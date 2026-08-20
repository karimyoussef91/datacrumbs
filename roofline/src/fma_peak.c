#include <omp.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
  const long iterations = argc > 1 ? strtol(argv[1], NULL, 10) : 50000000L;
  const int threads = omp_get_max_threads();
  double result = 0.0;
  const double start = omp_get_wtime();

#pragma omp parallel reduction(+ : result)
  {
    double a0 = 1.000001, a1 = 1.000002, a2 = 1.000003, a3 = 1.000004;
    double a4 = 1.000005, a5 = 1.000006, a6 = 1.000007, a7 = 1.000008;
    const double x = 1.0000001;
    const double y = 0.9999999;

    for (long index = 0; index < iterations; ++index) {
      a0 = a0 * x + y;
      a1 = a1 * x + y;
      a2 = a2 * x + y;
      a3 = a3 * x + y;
      a4 = a4 * x + y;
      a5 = a5 * x + y;
      a6 = a6 * x + y;
      a7 = a7 * x + y;
    }
    result += a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;
  }

  const double elapsed = omp_get_wtime() - start;
  const double gflops = (double)threads * (double)iterations * 16.0 / elapsed / 1.0e9;
  printf("threads=%d\n", threads);
  printf("elapsed_seconds=%.6f\n", elapsed);
  printf("gflops=%.6f\n", gflops);
  printf("checksum=%.6f\n", result);
  return result == 0.0;
}