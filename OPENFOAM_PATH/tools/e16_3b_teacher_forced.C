/**
 * @file e16_3b_teacher_forced.C
 * Teacher-forced replay of C++ ObservationBuilder + PolicyRuntime on a Python
 * state tape (T, P, Ykey[8]). Uses live Tprev/YkeyPrev history buffers.
 *
 * Input:
 *   --tape state_tape.csv
 *   --mean obs_rms_mean.txt (19 floats)
 *   --var  obs_rms_var.txt  (19 floats)
 *   --policy policy.ts
 *   --conf 0.6
 *   --out of_replay.csv
 *
 * Tape columns (header required):
 *   step_index,T,P,Y0,Y1,Y2,Y3,Y4,Y5,Y6,Y7,py_flag,py_p,py_conf
 */

#include "policyFeatures.H"
#include "policyCApi.H"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <array>
#include <cmath>

static std::vector<double> readVec19(const char* path)
{
    std::ifstream in(path);
    if (!in)
    {
        std::cerr << "Cannot open " << path << "\n";
        std::exit(2);
    }
    std::vector<double> v;
    double x;
    while (in >> x) v.push_back(x);
    if (v.size() != 19)
    {
        std::cerr << path << " expected 19 floats, got " << v.size() << "\n";
        std::exit(2);
    }
    return v;
}

int main(int argc, char** argv)
{
    const char* tapePath = nullptr;
    const char* meanPath = nullptr;
    const char* varPath = nullptr;
    const char* policyPath = nullptr;
    const char* outPath = "of_replay.csv";
    double confThresh = 0.6;

    for (int i = 1; i < argc; ++i)
    {
        auto need = [&](const char* name) -> const char*
        {
            if (i + 1 >= argc)
            {
                std::cerr << "Missing value for " << name << "\n";
                std::exit(2);
            }
            return argv[++i];
        };
        if (!std::strcmp(argv[i], "--tape")) tapePath = need("--tape");
        else if (!std::strcmp(argv[i], "--mean")) meanPath = need("--mean");
        else if (!std::strcmp(argv[i], "--var")) varPath = need("--var");
        else if (!std::strcmp(argv[i], "--policy")) policyPath = need("--policy");
        else if (!std::strcmp(argv[i], "--out")) outPath = need("--out");
        else if (!std::strcmp(argv[i], "--conf")) confThresh = std::atof(need("--conf"));
        else
        {
            std::cerr << "Unknown arg " << argv[i] << "\n";
            return 2;
        }
    }
    if (!tapePath || !meanPath || !varPath || !policyPath)
    {
        std::cerr << "Usage: e16_3b_teacher_forced --tape ... --mean ... --var ..."
                     " --policy ... [--out ...] [--conf 0.6]\n";
        return 2;
    }

    ofRlChem::PolicyManifest man;
    man.obsMean = readVec19(meanPath);
    man.obsVar = readVec19(varPath);
    man.confidenceThreshold = confThresh;
    man.modelPath = policyPath;

    void* handle = ofRlPolicy_load(policyPath);
    if (!handle)
    {
        std::cerr << "ofRlPolicy_load failed\n";
        return 2;
    }

    std::ifstream tape(tapePath);
    if (!tape)
    {
        std::cerr << "Cannot open tape " << tapePath << "\n";
        return 2;
    }
    std::string header;
    std::getline(tape, header);

    std::ofstream out(outPath);
    out << "step_index,T,P,of_flag,of_conf,of_p,py_flag,py_p,py_conf,agree,margin\n";

    double Tprev = 0.0;
    double Yprev[8] = {0,0,0,0,0,0,0,0};
    bool hasPrev = false;
    int nTot = 0, nAgree = 0;

    std::string line;
    while (std::getline(tape, line))
    {
        if (line.empty()) continue;
        std::stringstream ss(line);
        std::string tok;
        std::vector<std::string> cols;
        while (std::getline(ss, tok, ',')) cols.push_back(tok);
        if (cols.size() < 14) continue;

        const int step = std::stoi(cols[0]);
        const double T = std::stod(cols[1]);
        const double P = std::stod(cols[2]);
        double Ykey[8];
        for (int j = 0; j < 8; ++j) Ykey[j] = std::stod(cols[3 + j]);
        const int pyFlag = std::stoi(cols[11]);
        const double pyP = std::stod(cols[12]);
        const double pyConf = std::stod(cols[13]);

        auto raw = ofRlChem::buildObservation19(
            T, P, Ykey, Tprev, Yprev, hasPrev
        );
        auto feat = ofRlChem::normalizeObs(raw, man);

        int flag = 0;
        double conf = 0.0, pQssVal = 0.0;
        ofRlPolicy_inferBatch(
            handle, feat.data(), 1, confThresh, &flag, &conf, &pQssVal
        );

        const int agree = (flag == pyFlag) ? 1 : 0;
        nTot += 1;
        nAgree += agree;
        const double margin = std::fabs(pQssVal - 0.5);

        out << step << ',' << T << ',' << P << ','
            << flag << ',' << conf << ',' << pQssVal << ','
            << pyFlag << ',' << pyP << ',' << pyConf << ','
            << agree << ',' << margin << '\n';

        Tprev = T;
        for (int j = 0; j < 8; ++j) Yprev[j] = Ykey[j];
        hasPrev = true;
        (void)step;
    }

    ofRlPolicy_free(handle);

    const double pct = (nTot > 0) ? (100.0 * nAgree / nTot) : 0.0;
    std::cout << "teacher_forced n=" << nTot
              << " agree=" << nAgree
              << " pct=" << pct << "\n";
    std::cout << "GATE_TEACHER " << ((pct >= 99.0) ? "PASS" : "FAIL")
              << " threshold=99%\n";
    return (pct >= 99.0) ? 0 : 1;
}
