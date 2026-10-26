import unittest

from tortuga import parse_tasks, render, validate


class TortugaTests(unittest.TestCase):
    def test_parses_and_preserves_explicit_dates(self):
        tasks = parse_tasks("# comentario\n[2026-10-24] Preparar material\nOrdenar notas")
        self.assertEqual(tasks, [
            {"id": "T1", "due": "2026-10-24", "text": "Preparar material"},
            {"id": "T2", "due": "", "text": "Ordenar notas"},
        ])

    def test_rejects_invented_or_duplicate_ids(self):
        tasks = parse_tasks("Uno\nDos")
        for ids in (("T3",), ("T1", "T1")):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate({"choices": [
                    {"id": item, "first_step": "Abrir la lista", "why_now": "Ayuda"}
                    for item in ids
                ]}, tasks)

    def test_valid_plan_includes_source_task(self):
        tasks = parse_tasks("[2026-10-24] Preparar material")
        plan = validate({"choices": [{"id": "T1", "first_step": "Leer inventario", "why_now": "Vence pronto"}]}, tasks)
        self.assertIn("Preparar material · vence 2026-10-24", render(plan))


if __name__ == "__main__":
    unittest.main()
