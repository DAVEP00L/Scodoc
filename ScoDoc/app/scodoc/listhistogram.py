import math


def ListHistogram(L, nbins, minmax=None):
    """Compute histogram of a list.
    Does not use Numeric or numarray.

    H[i] is the number of elements from L
    such that bins[i] <= L[i] < bins[i+1]
    """
    n = len(L)
    if minmax is None:
        xmin = min(L)
        xmax = max(L)
    else:
        xmin, xmax = minmax
        # clip data
        for i in range(n):
            if L[i] < xmin:
                L[i] = xmin
            if L[i] > xmax:
                L[i] = xmax
    bin_width = (xmax - xmin) / float(nbins - 1)
    H = [0] * nbins
    for i in range(n):
        idx = int(math.floor((L[i] - xmin) / bin_width))
        H[idx] += 1
    bins = []
    for i in range(nbins):
        bins.append(xmin + bin_width * i)
    return bins, H
