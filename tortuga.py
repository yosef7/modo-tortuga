"""A small, local first-step planner. No task service or cloud connection."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA = {
    "type": "object",
    "properties": {
        "choices": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "first_step": {"type": "string"},
                    "why_now": {"type": "string"},
                },
                "required": ["id", "first_step", "why_now"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["choices"],
    "additionalProperties": False,
}


def parse_tasks(raw: str) -> list[dict[str, str]]:
    """Read one task per line: optional YYYY-MM-DD deadline, then text."""
    tasks = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) > 300:
            raise ValueError("Cada pendiente debe tener 300 caracteres o menos")
        match = re.fullmatch(r"(?:\[(\d{4}-\d{2}-\d{2})\] )?(.+)", line)
        if not match:
            raise ValueError(f"Línea no reconocida: {line}")
        tasks.append({"id": f"T{len(tasks) + 1}", "due": match[1] or "", "text": match[2]})
    if not 1 <= len(tasks) <= 30:
        raise ValueError("Escribe entre 1 y 30 pendientes")
    return tasks


def prompt_for(tasks: list[dict[str, str]]) -> str:
    return (
        "Eres un asistente de planificación en español. Elige de uno a tres pendientes "
        "y da un primer paso concreto para cada uno, de unos 15 minutos o menos. "
        "El primer paso debe producir un resultado pequeño y comprobable; NO repitas "
        "ni reformules simplemente el título del pendiente. Ejemplo: para 'Preparar "
        "presentación', escribe 'Abrir un documento y anotar tres ideas principales'. "
        "Prefiere fechas próximas explícitas y tareas que desbloquean otras. "
        "Usa solo los identificadores y fechas de la lista. No inventes vencimientos, "
        "hechos completados, promesas ni contactos. No pidas enviar mensajes, pagar, "
        "borrar o publicar automáticamente. Responde SOLO JSON conforme al esquema.\n"
        + json.dumps(tasks, ensure_ascii=False)
    )


def ask_ollama(tasks: list[dict[str, str]], model: str, host: str) -> dict:
    if host != "http://127.0.0.1:11434":
        raise ValueError("Solo se permite Ollama local en 127.0.0.1:11434")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt_for(tasks)}],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
        "think": False,
    }).encode()
    request = urllib.request.Request(
        f"{host}/api/chat", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    return json.loads(payload["message"]["content"])


def validate(result: dict, tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Never present model-selected tasks that were not in the input."""
    by_id = {task["id"]: task for task in tasks}
    choices = result.get("choices")
    if not isinstance(choices, list) or not 1 <= len(choices) <= 3:
        raise ValueError("El modelo no devolvió entre uno y tres pasos")
    seen = set()
    clean = []
    for choice in choices:
        if not isinstance(choice, dict) or set(choice) != {"id", "first_step", "why_now"}:
            raise ValueError("Formato de respuesta inválido")
        task_id = choice["id"]
        if task_id not in by_id or task_id in seen:
            raise ValueError("El modelo eligió un pendiente inexistente o repetido")
        for field in ("first_step", "why_now"):
            if not isinstance(choice[field], str) or not 1 <= len(choice[field].strip()) <= 240:
                raise ValueError("El modelo devolvió texto vacío o demasiado largo")
        seen.add(task_id)
        clean.append({**by_id[task_id], **choice})
    return sorted(clean, key=lambda item: (not bool(item["due"]), item["due"], item["id"]))


def render(choices: list[dict[str, str]]) -> str:
    lines = ["Modo Tortuga · empieza por esto (propuesta; tú decides):"]
    for number, choice in enumerate(choices, 1):
        date = f" · vence {choice['due']}" if choice["due"] else ""
        lines += [f"{number}. {choice['text']}{date}",
                  f"   Primer paso: {choice['first_step']}",
                  f"   Motivo: {choice['why_now']}"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reduce una lista de pendientes a tres primeros pasos con IA local")
    parser.add_argument("file", type=Path, help="Archivo UTF-8: un pendiente por línea")
    parser.add_argument("--model", default="gemma4:e2b", help="Modelo local instalado en Ollama")
    args = parser.parse_args()
    try:
        tasks = parse_tasks(args.file.read_text(encoding="utf-8"))
        choices = validate(ask_ollama(tasks, args.model, "http://127.0.0.1:11434"), tasks)
        print(render(choices))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"No se generó un plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
