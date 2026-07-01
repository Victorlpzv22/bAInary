#include <stdio.h>

static int add(int a, int b) {
    return a + b;
}

static int mul(int a, int b) {
    return a * b;
}

int main(void) {
    int sum = 0;
    for (int i = 0; i < 5; i++) {
        sum = add(sum, i);
    }
    printf("sum=%d, mul=%d\n", sum, mul(sum, 2));
    return 0;
}
