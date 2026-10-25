"""Smoke tests for the S0-1 feature-4 coupled driver (temporary)."""
import time
from ngdesign import registry
from ngdesign.units.column.spec import _parse_params
from ngdesign.units.column.coupled import _solve_specs_full
from ngdesign.units.column.thermo_adapter import _ThermoBox

thermo = registry.create('thermo', 'pr')

def run(tag, params_dict, top_p, bot_p):
    gf = {'T': 330.0, 'P': 1.5e6, 'molar_flow': 100.0, 'composition': {'C3': 0.5, 'iC4': 0.5}}
    t0 = time.time()
    try:
        c = _solve_specs_full(_parse_params(params_dict, gf), _ThermoBox(thermo, top_p, bot_p))
        dt = time.time() - t0
        return c, dt, None
    except Exception as e:
        return None, time.time() - t0, f'{type(e).__name__}: {str(e)[:200]}'

# Case 1: free pumparound driven by duty spec
p1 = {'n_stages': 12, 'condenser': 'total', 'reboiler': 'kettle', 'feed_stage': 6, 'pressure_profile': 1.5e6,
      'pumparounds': [{'name': 'pa', 'draw_stage': 10, 'return_stage': 6, 'return_T_K': 315.0}],
      'specs': {'reflux_ratio': 2.5, 'distillate_rate': 45.0, 'pumparound_duty': {'name': 'pa', 'value': -5e3}}}
c, dt, err = run('free-PA', p1, 1.5e6, 1.5e6)
if err:
    print(f'free-PA FAILED ({dt:.0f}s): {err}')
else:
    rep = c.prof.pa_report[0]
    print(f'free-PA {dt:.0f}s: pa flow {c.col.pumparounds[0].flow_mol_s:.8f} duty {rep["duty_W"]:.8f} '
          f'(err {rep["duty_W"]+5e3:.3g} W) d={c.prof.d:.8f} RR={c.prof.l0/max(c.prof.d,1e-12):.8f}')

# Case 2: coupled steam stripper driven by product_rate
p2 = {'n_stages': 16, 'condenser': 'total', 'reboiler': 'kettle', 'feed_stage': 8, 'pressure_profile': 1.5e6,
      'side_strippers': [{'name': 'ss', 'draw_stage': 12, 'return_stage': 9, 'n_stages': 4,
                          'steam': {'flow_mol_s': 1.0, 'T_K': 550.0, 'P_Pa': 1.6e6},
                          'product_rate_mol_s': 8.0}],
      'specs': {'reflux_ratio': 2.5, 'distillate_rate': 40.0}}
c, dt, err = run('stripper', p2, 1.5e6, 1.6e6)
if err:
    print(f'stripper FAILED ({dt:.0f}s): {err}')
else:
    rep = c.reports[0]
    print(f'stripper {dt:.0f}s: draw {c.strip_draws["ss"]:.6f} product {rep.product_flow:.8f} '
          f'(target 8, err {rep.product_flow-8:.3g})')
    print(f'  overhead return {rep.overhead_flow:.6f} mol/s at {rep.overhead_T:.3f} K; '
          f'main d={c.prof.d:.6f} b={c.prof.b:.6f}')
    print('  product comp: ' + ', '.join(f'{k}:{v:.4f}' for k, v in rep.product_comp.items()))
print('DONE')
