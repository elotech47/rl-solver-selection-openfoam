/**
 * @file qss_int.C
 * @brief CHEMEQ2 / α-QSS integrator implementation (OpenFOAM port)
 */

#include "qss_int.H"

#include <algorithm>
#include <cmath>
#include <iostream>

namespace ofRlChem
{
namespace
{
inline int sign(double x)
{
    return (x > 0) ? 1 : ((x < 0) ? -1 : 0);
}

inline bool notnan(const std::vector<double>& v)
{
    for (double val : v)
    {
        if (std::isnan(val)) return false;
    }
    return true;
}
} // namespace

void QssIntegrator::setOde(QssOde* ode)
{
    ode_ = ode;
}

void QssIntegrator::initialize(std::size_t neq)
{
    N_ = neq;
    y_.assign(N_, 0);
    q_.assign(N_, 0);
    d_.assign(N_, 0);
    rtaus_.assign(N_, 0);
    y1_.assign(N_, 0);
    ys_.assign(N_, 0);
    rtau_.assign(N_, 0);
    qs_.assign(N_, 0);
    ym1_.assign(N_, 0);
    ym2_.assign(N_, 0);
    scratch_.assign(N_, 0);
    ymin.assign(N_, 1e-20);
    enforce_ymin.assign(N_, 1.0);
    ymax.assign(N_, 1e30);
    enforce_ymax.assign(N_, 0.0);
}

void QssIntegrator::setState(const std::vector<double>& yIn, double tstart)
{
    for (std::size_t i = 0; i < N_; ++i)
    {
        y_[i] = enforce_ymin[i] ? std::max(yIn[i], ymin[i]) : yIn[i];
    }
    gcount_ = 0;
    rcount_ = 0;
    tstart_ = tstart;
    tn_ = 0.0;
    firstStep_ = true;
}

void QssIntegrator::getState(std::vector<double>& yOut) const
{
    yOut = y_;
}

void QssIntegrator::getInitialStepSize(double tf)
{
    firstStep_ = false;
    double scratch_value = 1.0e-25;

    for (std::size_t i = 0; i < N_; ++i)
    {
        if (!enforce_ymin[i]) continue;
        if (std::abs(y_[i]) > abstol)
        {
            const double absq = std::abs(q_[i]);
            const double scr2 =
                std::abs(1.0 / y_[i])
                * static_cast<double>(sign(0.1 * epsmin * absq - d_[i]));
            const double scr1 = scr2 * d_[i];
            scratch_value = std::max
            (
                std::max(scr1, -std::abs(absq - d_[i]) * scr2),
                scratch_value
            );
        }
    }

    const double sqreps = 0.5;
    dt_ = std::min(sqreps / scratch_value, tf);
    dt_ = std::min(dt_, dtmax);
}

int QssIntegrator::integrateToTime(double tf_abs)
{
    const double tf_rel = tf_abs - tstart_;
    if (tf_rel < 0.0) return -2;
    while (tfd * tn_ < tf_rel)
    {
        const int ret = integrateOneStep(tf_rel);
        if (ret != 0) return ret;
        ++acceptedSteps_;
    }
    return 0;
}

int QssIntegrator::integrateOneStep(double tf_rel)
{
    ode_->odefun(tn_ + tstart_, y_, q_, d_);
    gcount_ += 1;

    if (firstStep_)
    {
        getInitialStepSize(tf_rel);
    }

    ts_ = tn_;
    for (std::size_t i = 0; i < N_; ++i)
    {
        rtau_[i] = enforce_ymin[i] ? dt_ * d_[i] / y_[i] : 0.0;
    }
    qs_ = q_;
    ys_ = y_;
    rtaus_ = rtau_;

    while (true)
    {
        for (std::size_t i = 0; i < N_; ++i)
        {
            const double denom =
                1.0
                + rtau_[i]
                      * (180 + rtau_[i] * (60 + rtau_[i] * (11 + rtau_[i])))
                      / (360 + rtau_[i] * (60 + rtau_[i] * (12 + rtau_[i])));
            scratch_[i] = (q_[i] - d_[i]) / denom;
        }

        double eps = 1e-10;
        for (int iter = 0; iter < itermax; ++iter)
        {
            if (stabilityCheck)
            {
                ym2_ = ym1_;
                ym1_ = y_;
            }

            for (std::size_t i = 0; i < N_; ++i)
            {
                double new_val = ys_[i] + dt_ * scratch_[i];
                new_val = std::max(new_val, ymin[i]);
                if (enforce_ymax[i]) new_val = std::min(new_val, ymax[i]);
                y_[i] = new_val;
            }

            if (iter == 0)
            {
                tn_ = ts_ + dt_;
                y1_ = y_;
            }

            ode_->odefun(tn_ + tstart_, y_, q_, d_, true);
            gcount_ += 1;

            std::vector<double> rtaub(N_);
            for (std::size_t i = 0; i < N_; ++i)
            {
                rtaub[i] =
                    enforce_ymin[i]
                        ? 0.5 * (rtaus_[i] + dt_ * d_[i] / y_[i])
                        : 0.0;
            }

            std::vector<double> alpha(N_);
            for (std::size_t i = 0; i < N_; ++i)
            {
                alpha[i] =
                    (180. + rtaub[i] * (60. + rtaub[i] * (11. + rtaub[i])))
                    / (360. + rtaub[i] * (60. + rtaub[i] * (12. + rtaub[i])));
            }

            for (std::size_t i = 0; i < N_; ++i)
            {
                if (!enforce_ymin[i])
                {
                    scratch_[i] = q_[i] - d_[i];
                }
                else
                {
                    scratch_[i] =
                        (qs_[i] * (1.0 - alpha[i]) + q_[i] * alpha[i]
                         - ys_[i] * rtaub[i] / dt_)
                        / (1.0 + alpha[i] * rtaub[i]);
                }
            }
        }

        eps = 0.0;
        for (std::size_t i = 0; i < N_; ++i)
        {
            double new_y = ys_[i] + dt_ * scratch_[i];
            if (enforce_ymin[i]) new_y = std::max(new_y, ymin[i]);
            if (enforce_ymax[i]) new_y = std::min(new_y, ymax[i]);
            double error = std::abs(new_y - y1_[i]);
            new_y = std::max(new_y, ymin[i]);
            if (enforce_ymax[i]) new_y = std::min(new_y, ymax[i]);
            y_[i] = new_y;

            if
            (
                enforce_ymin[i] && std::abs(y_[i]) > abstol
                && 0.25 * (ys_[i] + y_[i]) > ymin[i]
            )
            {
                error /= y_[i];
                eps = std::max
                (
                    0.5
                        * (error
                           + std::min
                             (
                                 std::abs(q_[i] - d_[i]) / (q_[i] + d_[i] + 1e-30),
                                 error
                             )),
                    eps
                );
            }
            else if (!enforce_ymin[i])
            {
                eps = std::max(error / std::max(std::abs(y_[i]), ymin[i]), eps);
            }
        }

        if (stabilityCheck)
        {
            ym2_ = ym1_;
            ym1_ = y_;
        }

        eps /= epsmin;

        if (dt_ <= dtmin + 1e-16 * tn_)
        {
            if (verbose > 0)
            {
                std::cerr << "QssIntegrator failed: timestep too small: dt="
                          << dt_ << " tn=" << tn_ << "\n";
            }
            return -1;
        }

        double stab = 0;
        if (stabilityCheck && itermax >= 3)
        {
            stab = 0.01;
            for (std::size_t i = 0; i < N_; ++i)
            {
                if (std::abs(y_[i]) > abstol)
                {
                    stab = std::max
                    (
                        stab,
                        std::abs(y_[i] - ym1_[i])
                            / (std::abs(ym1_[i] - ym2_[i]) + 1e-20 * y_[i])
                    );
                }
            }
        }

        if (eps <= epsmax && stab <= 1.0)
        {
            if (tf_rel <= tn_ * tfd) return 0;
        }
        else
        {
            tn_ = ts_;
        }

        double rteps = 0.5 * (eps + 1.0);
        rteps = 0.5 * (rteps + eps / rteps);
        rteps = 0.5 * (rteps + eps / rteps);

        const double dto = dt_;
        dt_ = std::min(dt_ * (1.0 / rteps + 0.005), tfd * (tf_rel - tn_));
        dt_ = std::min(dt_, dtmax);
        if (stabilityCheck)
        {
            dt_ = std::min(dt_, dto / (stab + 0.001));
        }

        if (eps > epsmax || stab > 1.0)
        {
            rcount_ += 1;
            for (std::size_t i = 0; i < N_; ++i)
            {
                rtaus_[i] *= dt_ / dto;
            }
        }
        else
        {
            return 0;
        }
    }
}

} // namespace ofRlChem
