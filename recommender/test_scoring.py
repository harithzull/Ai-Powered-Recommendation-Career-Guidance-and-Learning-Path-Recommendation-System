from django.test import SimpleTestCase
from recommender.scoring import normalized_riasec


class RiasecScoringTests(SimpleTestCase):
    def test_average_not_sum(self):
        result = normalized_riasec([('I', 5), ('I', 1), ('R', 3)])
        self.assertEqual(result['I'], 0.6)
        self.assertEqual(result['R'], 0.6)

    def test_missing_types_are_zero(self):
        result = normalized_riasec([('A', 5)])
        self.assertEqual(result['A'], 1.0)
        self.assertEqual(result['S'], 0.0)

    def test_empty_answers(self):
        self.assertEqual(normalized_riasec([]), {t: 0.0 for t in 'RIASEC'})
