# 1

### What were the most difficult parts of Anymalign to understand?

- The transaction prob / lexical weight part.

### Why (because too many versions, because too many papers, etc.)?

- Because I didn't realize the **one-to-many** thing at first.

# 2

### What are the advantages of Anymalign over other subsentential alignment tools or techniques?

- not even trying to depend on huge data

- solid theoretical use of hapax

- memory conservative

- scalable to multiple processes, even computers

### Can you name some of these tools or techniques?

- Giza++
- grow-diag-final

# 3

### The ultimate goal is to have Anymalign do a better job than Giza++/Moses in conjonction with the Moses SMT engine builder.

### Can you suggest how to achieve this goal?

- run more instances of anymalign, and merge the alignments afterward

### Can you justify your suggestion?

- anymalign

# 4

Anymalign has been designed for subsentential alignment

Can you imagine other applications of Anymalign, possibly in totally unrelated domains?

the kernel idea is "collocation"
in NLP: unsupervised phrase mining?

