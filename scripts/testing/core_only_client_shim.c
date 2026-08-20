#include <stdlib.h>

void datacrumbs_start(void);
void datacrumbs_stop(void);

__attribute__((constructor)) static void enable_datacrumbs(void) {
  datacrumbs_start();
}

__attribute__((destructor)) static void disable_datacrumbs(void) {
  datacrumbs_stop();
}