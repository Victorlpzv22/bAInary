static int c(void) { return 42; }
static int b(void) { return c() + 1; }
int a(void) { return b() + 1; }
int main(void) { return a(); }
