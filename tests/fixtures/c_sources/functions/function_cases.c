#define MacroLike(x) ((x) + 1)

int PrototypeOnly(int value);
int (*PointerLike)(int value);

const char *noise = "int StringNoise(void) { return 0; }";
/* int CommentNoise(void) { return 0; } */

static int StaticFunction(int value)
{
    if (value > 0) {
        return value;
    }
    return 0;
}

int
MultilineHeader(
    int value
)
{
    return value + 1;
}

int OldStyle(value)
int value;
{
    return value;
}

#if 0
int ConditionalDuplicate(void)
{
    return 0;
}
#else
int ConditionalDuplicate(void)
{
    return 1;
}
#endif

void Caller(void)
{
    StaticFunction(1);
}

int Broken(void)
{
    return 1;
