#ifndef AIRC_TASK_UI_H
#define AIRC_TASK_UI_H

/* Console task visibility: English description, spinner, DONE/FAIL colours. */

void task_ui_set_enabled(int on);
void task_ui_begin(const char *job_json);
void task_ui_spin_tick(void);
void task_ui_end(const char *result_json);

#endif
