/**
 * @file qss_int.H
 * @brief CHEMEQ2 / α-QSS integrator (OpenFOAM port, no AMReX)
 *
 * Based on Mott, Oran & van Leer (2000) and PelePhysics qss_int.
 * ODE split: dy/dt = q(y) - d(y).
 */

#ifndef of_rl_chem_qss_int_H
#define of_rl_chem_qss_int_H

#include <cstddef>
#include <vector>

namespace ofRlChem
{

/** Abstract ODE interface: production q and destruction d. */
class QssOde
{
public:
    virtual ~QssOde() = default;
    virtual void odefun
    (
        double t,
        const std::vector<double>& y,
        std::vector<double>& q,
        std::vector<double>& d,
        bool corrector = false
    ) = 0;
};

/** Advance y from tstart to tf with adaptive CHEMEQ2 substeps. */
class QssIntegrator
{
public:
    QssIntegrator() = default;

    void setOde(QssOde* ode);
    void initialize(std::size_t neq);
    void setState(const std::vector<double>& yIn, double tstart);
    int integrateToTime(double tf_abs);
    void getState(std::vector<double>& yOut) const;
    double integratedTime() const { return tn_; }

    // Paper / handoff defaults
    double epsmax{100.0};
    double epsmin{0.02};
    double dtmin{1e-12};
    double dtmax{1e-6};
    int itermax{2};
    double tfd{1.000008};
    double abstol{1e-11};
    bool stabilityCheck{true};
    int verbose{0};

    std::vector<double> ymin;
    std::vector<double> enforce_ymin;
    std::vector<double> ymax;
    std::vector<double> enforce_ymax;

private:
    void getInitialStepSize(double tf);
    int integrateOneStep(double tf_rel);

    QssOde* ode_{nullptr};
    std::size_t N_{0};
    bool firstStep_{true};
    double dt_{0};
    double ts_{0};
    double tstart_{0};
    double tn_{0};
    int gcount_{0};
    int rcount_{0};
    int acceptedSteps_{0};

    std::vector<double> y_, q_, d_, rtaus_, y1_, ys_, rtau_, qs_;
    std::vector<double> ym1_, ym2_, scratch_;
};

} // namespace ofRlChem

#endif
