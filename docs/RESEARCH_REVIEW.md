# Research links and their implementation role

## Sustainable inventory and transport

**Mundim, Santos & Morabito (2025).** *Sustainable solutions analysis of a bi-objective green inventory routing problem with heterogeneous fleet and different types of fuels.* RAIRO–Operations Research 59, 549–578. https://doi.org/10.1051/ro/2024162

Sections 4 and 5.3 support integrating inventory and routing and using emissions-constrained cost optimisation. Table 5 was inspected in the accessible author full-text listing and gives diesel combustion CO₂ of 2.66 kg/L. The monthly scenario now uses that factor with explicit source attribution. Fuel consumption, distance scaling and costs remain assumptions. We implement a simpler distance-based equation and complete-route MILP, not a reproduction of the paper's full vehicle equation or augmented epsilon procedure. Published experimental savings are not our outcomes.

Accessible text: https://www.researchgate.net/publication/383196437_Sustainable_solutions_analysis_of_a_bi-objective_green_inventory_routing_problem_with_heterogeneous_fleet_and_different_types_of_fuels

**Benjaafar, Li & Daskin (2013).** *Carbon Footprint and the Management of Supply Chains: Insights From Simple Models.* IEEE Transactions on Automation Science and Engineering 10(1), 99–116. https://doi.org/10.1109/TASE.2012.2203304

The authors examine how carbon parameters and emissions policies can enter operational models. This motivates exposing both cost and emissions rather than assuming they always improve together. We do not replicate their collaboration or regulatory-policy analyses.

Author institutional record: https://experts.umn.edu/en/publications/carbon-footprint-and-the-management-of-supply-chains-insights-fro/

## Sparse sales forecasting

**Teunter, Syntetos & Babai (2011).** *Intermittent demand: Linking forecasting to inventory obsolescence.* European Journal of Operational Research 214, 606–615. https://doi.org/10.1016/j.ejor.2011.05.018

Section 3's probability/size formulation is used for TSB, with fixed alpha/beta settings documented in ALGORITHMS.md. The method adjusts occurrence probability on zero-demand periods. Our model-ranking results are computed from M5 and are not taken from this paper.

Author-hosted paper: https://pure.rug.nl/ws/portalfiles/portal/145394864/Intermittent_demand_Linking_forecasting_to_inventory_obsolescence.pdf

**Syntetos & Boylan (2005).** *The accuracy of intermittent demand estimates.* International Journal of Forecasting 21(2), 303–314. https://doi.org/10.1016/j.ijforecast.2004.10.001

Provides the rationale for the Croston–SBA bias correction included as a statistical benchmark. Institutional record: https://orca.cardiff.ac.uk/id/eprint/65452/

## Sustainable development connections

- UN SDG 12: https://sdgs.un.org/goals/goal12 — motivation for resource-conscious operating decisions. The prototype does not estimate official material-footprint indicators.
- UN SDG 13: https://sdgs.un.org/goals/goal13 — motivation for examining transport-emissions consequences. The prototype is not a certified corporate carbon inventory or evidence of actual emissions abatement.

All dashboard outcome figures come from local simulation exports, not from these references. Results may show increases, and a lower-emissions plan is not qualified as an improvement if service deteriorates.
