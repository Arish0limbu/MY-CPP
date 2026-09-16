#include <iostream>
#include <string.h>

using namespace std;

void line(int l = 100)
{
    for (int i = 0; i < l; i++)
    {
        cout << "=";
    }
    cout << endl;
}

void space(int s = 45)
{
    for (int i = 0; i < s; i++)
    {
        cout << " ";
    }
}

void clearscreen()
{
#ifdef WIN32
    system("cls");
#else
    system("clear");
#endif
}

void header(string heading)
{
    int count = 0;
    clearscreen();
    for (int i = 0; heading[i] != '\0'; i++)
    {
        count++;
    }
    line();
    space((100 - count) / 2);
    cout << heading << endl;
    line();
}

int main()
{
    header("|| LOGIN PAGE ||");
    return 0;
}