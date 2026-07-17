/**
 * Standalone unit test for CHEMEQ2 absolute-time integration (no OpenFOAM).
 * Build: c++ -O2 -std=c++17 -o test_qss_int tests/test_qss_int_standalone.cpp \
 *          src/qssChemistrySolver/qss_int.C -I src/qssChemistrySolver
 */
#include "qss_int.H"
#include <cmath>
#include <iostream>
#include <vector>

using namespace ofRlChem;

struct DecayOde : QssOde
{
    // dy/dt = 0 - y  => q=0, d=y  exponential decay
    void odefun(
        double,
        const std::vector<double>& y,
        std::vector<double>& q,
        std::vector<double>& d,
        bool) override
    {
        q.assign(y.size(), 0.0);
        d = y;
    }
};

int main()
{
    DecayOde ode;
    QssIntegrator integ;
    integ.epsmin = 0.02;
    integ.epsmax = 100;
    integ.dtmin = 1e-16;
    integ.dtmax = 1e-3;
    integ.abstol = 1e-14;
    integ.itermax = 2;
    integ.initialize(1);
    integ.setOde(&ode);
    std::vector<double> y = {1.0};
    const double dt = 1e-6;
    integ.setState(y, 0.0);
    const int ret = integ.integrateToTime(dt);
    if (ret != 0)
    {
        std::cerr << "FAIL ret=" << ret << "\n";
        return 1;
    }
    const double t = integ.integratedTime();
    const double err = std::abs(t - dt);
    std::cout << "integrated_time=" << t << " requested=" << dt
              << " abs_err=" << err << "\n";
    if (err > 1e-12)
    {
        std::cerr << "FAIL time mismatch\n";
        return 2;
    }
    integ.getState(y);
    std::cout << "y_final=" << y[0] << " (expect ~exp(-dt)=" << std::exp(-dt)
              << ")\n";
    std::cout << "PASS\n";
    return 0;
}
