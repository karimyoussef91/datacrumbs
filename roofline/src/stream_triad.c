#include <omp.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
  const size_t count = argc > 1 ? strtoull(argv[1], NULL, 10) : 50000000ULL;
  const int repetitions = argc > 2 ? atoi(argv[2]) : 8;
  const int threads = omp_get_max_threads();
  const double scalar = 3.0;
  double *a = NULL;
  double *b = NULL;
  double *c = NULL;

  if (posix_memalign((void **)&a, 64, count * sizeof(*a)) ||
      posix_memalign((void **)&b, 64, count * sizeof(*b)) ||
      posix_memalign((void **)&c, 64, count * sizeof(*c))) {
    fprintf(stderr, "allocation failed for %zu elements\n", count);
    free(a);
    free(b);
    free(c);
    return 1;
  }

#pragma omp parallel for schedule(static)
  for (size_t index = 0; index < count; ++index) {
    a[index] = 1.0;
    b[index] = 2.0;
    c[index] = 0.0;
  }

  double best_seconds = 1.0e100;
  for (int repetition = 0; repetition < repetitions; ++repetition) {
    const double start = omp_get_wtime();
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < count; ++index) {
      c[index] = a[index] + scalar * b[index];
    }
    const double elapsed = omp_get_wtime() - start;
    if (elapsed < best_seconds) best_seconds = elapsed;
  }

  const double bandwidth_gbs = (double)count * 24.0 / best_seconds / 1.0e9;
  printf("threads=%d\n", threads);
  printf("elements=%zu\n", count);
  printf("best_seconds=%.6f\n", best_seconds);
  printf("bandwidth_gbs=%.6f\n", bandwidth_gbs);
  printf("checksum=%.6f\n", c[count / 2]);
  free(a);
  free(b);
  free(c);
  return 0;
}