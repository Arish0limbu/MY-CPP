#include <iostream>
using namespace std;

class Complex
{
private:
    int real, imag;

public:
    void input()
    {
        cout << "Enter real and imaginary part: ";
        cin >> real >> imag;
    }

    void display()
    {
        cout << real;

        if (imag >= 0)
            cout << " + " << imag << "i";
        else
            cout << " - " << -imag << "i";
    }

    Complex operator-(Complex c)
    {
        Complex temp;

        temp.real = real - c.real;
        temp.imag = imag - c.imag;

        return temp;
    }
};

int main()
{
    Complex c1, c2, c3;

    cout << "Enter first complex number:" << endl;
    c1.input();

    cout << "Enter second complex number:" << endl;
    c2.input();

    c3 = c1 - c2;

    cout << "Difference = ";
    c3.display();

    return 0;
}