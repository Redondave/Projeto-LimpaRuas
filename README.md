# Urban Traffic Intervention Analysis

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

Optimization of the **Speed Performance Index (K)** in the road network of Gama (Federal District, Brazil). This project integrates regional graph generation, Origin-Destination (OD) matrix creation from floating-car data, observed link speeds, and road physical attributes to model traffic assignment via the **Frank-Wolfe algorithm**.

---

## 📌 Key Features

- **Spatial Graph Construction:** 134-node, 236-edge expanded network generated from OpenStreetMap (OSM) data.
- **Empirical Calibration:** Origin-Destination matrix calibrated using TomTom Traffic Stats and local DETRAN-DF volume count sensors.
- **Traffic Assignment Engine:** Custom Frank-Wolfe User Equilibrium (UE) implementation supporting multiple demand levels and BPR link performance functions.
- **Braess Paradox Scanning:** Systematic single-edge closure and capacity expansion sweeps to detect network performance anomalies.
- **Interactive Dashboards:** Automated HTML visualizer for spatial flow distributions, convergence metrics, and scenario comparisons.

---

## 📁 Repository Structure

```text
.
├── cache/                  # Processed network graphs, geojson gates, and spatial caches
├── Tables/                 # Calibrated OD matrices, TomTom speed stats, and road attributes
├── cenarios/               # JSON definitions for road intervention scenarios (C0, F*, S*, R*)
├── scripts/                # Data processing, graph expansion, and assignment scripts
├── research/               # Methodology plans, logs, and scenario reports
└── resultados/             # Output files from Frank-Wolfe runs, panel dashboard, and paper figures

```

## 👥 Authors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/daviggalvao">
        <img src="https://github.com/daviggalvao.png?size=100" width="100px;" alt="Photo of Davi Galvão"/>
        <br />
        <sub>
          <b>Davi Galvão</b>
        </sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Redondave">
        <img src="https://github.com/Redondave.png?size=100" width="100px;" alt="Photo of Davi Brasileiro"/>
        <br />
        <sub>
          <b>Davi Brasileiro</b>
        </sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Liferoijrm">
        <img src="https://github.com/Liferoijrm.png?size=100" width="100px;" alt="Photo of Pedro Marcinoni"/>
        <br />
        <sub>
          <b>Pedro Marcinoni</b>
        </sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Leo3107">
        <img src="https://github.com/Leo3107.png?size=100" width="100px;" alt="Photo of Leonardo Mileo"/>
        <br />
        <sub>
          <b>Leonardo Mileo</b>
        </sub>
      </a>
    </td>
  </tr>
</table>
