#include <iostream>
#include <fstream>

using namespace std;

int main()
{
    ifstream file;
    file.open("demo.txt");
    if (file.is_open())
    {
        cout << "File open successfully. " << endl;
    }
    else
    {
        cout << "File is not open." << endl;
    }
    file.close();
    if (!file.is_open())
    {
        cout << "File close successfully." << endl;
    }
    else
    {
        cout << "File is still open." << endl;
    }
    ofstream editor;
    editor.open("student.txt");
    if (editor.is_open())
    {
        cout << "File open successfully. " << endl;
    }
    else
    {
        cout << "File is not open." << endl;
    }
    editor << "HEllo";
    editor.close();

    fstream both;
    both.open("student.txt", ios::in | ios::out);

    both.close();
}