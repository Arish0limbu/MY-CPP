#include <iostream>

using namespace std;

class time
{
private:
    int hour, minute, second;

public:
    void input()
    {
        cout << "Enter 1st time........" << endl;
        cout << "Enter Hour: ";
        cin >> hour;
        cout << "Enter Minute: ";
        cin >> minute;
        cout << "Enter Second: ";
        cin >> second;
    }

    void display()
    {
        cout << "Your Total time........." << endl;
        cout << hour << ":" << minute << ":" << second;
    }

    time add(time t)
    {
        t.input();
    }
};