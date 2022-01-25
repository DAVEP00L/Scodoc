"""Script pour faciliter le lancement de benchmarks
"""

from tests.bench.notes_table import bench_notes_table

BENCH_DEPT = "RT"
BENCH_FORMSEMESTRE_IDS = (
    149,  # RT S1 2020-21
    145,  # RT S2 2021
    119,  # RT S1 2029
)

bench_notes_table(BENCH_DEPT, BENCH_FORMSEMESTRE_IDS)
