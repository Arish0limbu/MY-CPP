#include <iostream>

using namespace std;

class interest
{
private:
    float p, t, r, si;

public:
    void input()
    {
        cout << "Enter p t r: ";
        cin >> p >> t >> r;
    }

    void calculate()
    {
        si = (p * t * r)/100;
    }

    void display()
    {
        cout << "Simple interest is= " << si;
    }
};

interest simple(interest obj)
{
    obj.calculate();
    return obj;
}

int main()
{
    interest a,b;
    a.input();
    b = simple(a);
    b.display();
    return 0;
}