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

string login()
{
    int option;
    string pass, id;

    header("|| LOGIN PAGE ||");
    cout << "1)ADMIN LOGIN." << endl
         << "2)EMPLOYEE LOGIN." << endl
         << "3)EXIT SYSTEM." << endl;
    line();
    cout << "Enter the number to select login portal: ";
    cin >> option;
    switch (option)
    {
    case 1:
        header("|| ADMIN LOGIN PAGE ||");
        cout << "ID: ";
        cin >> id;
        cout << "PASSWORD: ";
        cin >> pass;
        if (id == "123" && pass == "123")
        {
            return "admin";
        }
        else
            break;

    case 2:
        header("|| EMPLOYEE LOGIN PAGE ||");
        cout << "ID: ";
        cin >> id;
        cout << "PASSWORD: ";
        cin >> pass;
        if (id == "1" && pass == "1")
        {
            return "employe";
        }
        else
            break;

    case 3:
        return 0;
    default:
        return 0;
    }
}
int main()
{
    if (login() == "admin")
    {
        cout << "Hello";
    }
    else if (login() == "employe")
    {
        cout << " now";
    }
    else
    return 0;
}