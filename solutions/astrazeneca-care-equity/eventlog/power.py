"""Exact normal quantiles implement section 2, without rounded table constants.

sample_size(r, sigma) is the one formula; what changes between the idealised
and the realistic table is only sigma: 0.96 for a single log-normal step, or
the standard deviation of log-duration measured for each core interval in a
large simulated sample (design_study.calibrate).

Two refinements, both stated in DATA_COLLECTION.md:
  national=N    the comparator is the rest of the country in the same period,
                N - n episodes, not an infinite reference: n(N - n)/N replaces n.
  comparisons   counts every test in the family. One look at 23 counties x 3
                intervals is 69. L planned looks make it 69 x L (Bonferroni over
                looks, an upper bound for overlapping rolling windows).
The detector itself (detect.test_moments) uses Welch t quantiles; critical(df=...)
gives them. The formulas here stay the normal approximation the document states.
"""
from math import ceil, exp, log, sqrt
from statistics import NormalDist
from scipy.special import stdtrit
NORM = NormalDist()
IDEAL_SIGMA = .96
ZERO_DAY = .5  # a zero-day interval is logged as 0.5 day; positive intervals are unchanged
MIN_TEST_N = 30  # fewer complete day-precision episodes than this are summarised but not tested

def critical(alpha=.05, comparisons=69, df=None):
    """Two-sided Bonferroni critical value: normal, or Student t with df degrees of freedom."""
    p = 1-alpha/(2*comparisons)
    return NORM.inv_cdf(p) if df is None else stdtrit(df, p)

def required_information(r, sigma=IDEAL_SIGMA, power=.8, alpha=.05, comparisons=69):
    """s^2 (z + z_power)^2 / (ln r)^2: the n needed against an infinite reference."""
    if r<=1: raise ValueError('r > 1 required')
    return sigma**2*(critical(alpha,comparisons)+NORM.inv_cdf(power))**2/log(r)**2

def sample_size(r, sigma=IDEAL_SIGMA, power=.8, alpha=.05, comparisons=69, missingness=0., national=None):
    """Complete episodes needed in the county. With national=N the comparator is the
    other N - n episodes of the same period; returns None when no county size reaches
    the power (the county would have to be more than half of the country)."""
    if not 0<=missingness<1: raise ValueError('r > 1 and 0 <= missingness < 1 required')
    k = required_information(r,sigma,power,alpha,comparisons)
    if national is not None:
        if 4*k>national: return None
        k = (national-sqrt(national*national-4*k*national))/2
    return ceil(k/(1-missingness))

def min_detectable_ratio(n, sigma, national=None, power=.8, alpha=.05, comparisons=69):
    """Smallest slowdown ratio detectable with the stated power from n complete episodes."""
    if n<=0 or (national is not None and n>=national): return None
    return exp(sigma*(critical(alpha,comparisons)+NORM.inv_cdf(power))*sqrt(1/n+(1/(national-n) if national else 0.)))

def binomial_size(p0=.7,p1=.6,power=.8,alpha=.05,comparisons=69):
    return ceil((critical(alpha,comparisons)*sqrt(p0*(1-p0))+NORM.inv_cdf(power)*sqrt(p1*(1-p1)))**2/(p0-p1)**2)

def analytic_power(r,n,sigma=IDEAL_SIGMA,reference_n=float('inf'),comparisons=69):
    if n<=0: return 0.
    delta = log(r)/(sigma*sqrt(1/n+1/reference_n)); z=critical(comparisons=comparisons)
    return 1-NORM.cdf(z-delta)+NORM.cdf(-z-delta)
