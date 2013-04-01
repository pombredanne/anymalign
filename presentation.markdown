% how anymalign works
% john doe
% 2013-04-05

# Why subcorpura

# Size of subcorpura - Goal

## We demand the same cover rate C% ,    \
from **subcorpus of different size** .

`N := number of all corpus`

`p(k) := probability that corpora has size k`

In T subcorpus , we want

- $T \cdot p(1)$ 1-sentence subcorpus, which covers $N \cdot C $ sentences
- $T \cdot p(2)$ 2-sentence subcorpus, which covers $N \cdot C $ sentences
- ...

# Size of subcorpura - Modelling

After $T \cdot p(k) $ subcorpus of k-sentence are chosen,

the probability that a sentence *is not covered* is

$( (1-k/N)^k )^{ T \cdot p(k) } $

which equals to $1 - C$

# Size of subcorpura - Conclusion

From $( (1-k/N)^k )^{ T \cdot p(k) } = 1 - C$

we can obtain $p(k) = \dfrac{ \ln{(1-C)} }{kT \ln{(1-\frac{k}{N})}} $

or, simply $p(k) \propto \dfrac{-1}{k \ln{(1-\frac{k}{N})} } $

# wtf

hello

\begin{CJK}{UTF8}{min}日本語\end{CJK}
\begin{CJK}{UTF8}{song}中文\end{CJK}

    #!/bin/sh
    a
    bb
    cc
