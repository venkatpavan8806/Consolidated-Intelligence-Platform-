class UnionFind:
    """Standard disjoint-set with path compression + union by rank.

    Used instead of naive pairwise comparison so that N mentions of one
    ambiguous name land in ONE connected-component cluster rather than
    producing up to C(N,2) duplicate review-queue rows (see gotcha #2).
    """

    def __init__(self, items):
        self.parent = {x: x for x in items}
        self.rank = {x: 0 for x in items}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1

    def groups(self):
        out = {}
        for x in self.parent:
            root = self.find(x)
            out.setdefault(root, []).append(x)
        return list(out.values())
