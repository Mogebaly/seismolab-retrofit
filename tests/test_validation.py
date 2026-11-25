from retrofit import validation as V
def test_cantilever(): assert V.cantilever_deflection()[2] < 1e-6
def test_sdof_period(): assert V.sdof_period()[2] < 1e-4
def test_sdof_time_history_vs_independent_rk4(): assert V.sdof_time_history()[2] < 0.02
def test_frame_gravity_equilibrium(): assert V.frame_gravity_equilibrium()[2] < 1e-6
def test_column_pushover():
    r = V.column_pushover_checks(); assert r["above_Mp"] >= 0 and r["equilibrium_err"] < 1e-4

def test_column_no_hardening_matches_plastic_couple():
    r = V.column_pushover_checks(hardening=0.0); assert abs(r["above_Mp"]) < 0.05
