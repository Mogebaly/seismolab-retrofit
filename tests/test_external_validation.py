from retrofit import external_validation as X

def test_elastic_frame_matches_published_sap2000_values():
    periods, got = X.run()
    assert all(abs(p - r) < 1e-4 + 1e-9 for p, r in zip(periods, X.PERIODS_SAP2000))
    assert abs(got["disp_top"] - X.STATIC_SAP2000["disp_top"]) < 1e-3
    assert abs(got["axial_bottom_left"] - X.STATIC_SAP2000["axial_bottom_left"]) < 1e-2
    assert abs(got["moment_bottom_left"] - X.STATIC_SAP2000["moment_bottom_left"]) < 1e-2
