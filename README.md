anymalign
=========

a multilingual aligner for statistical machine translation

This is not the [official repo](http://anymalign.limsi.fr).

original author
==============
Adrien Lardilleux

original readme
==============
    Please visit http://users.info.unicaen.fr/~alardill/anymalign/ for details.
    
    
    ================================== Change log =================================
    
    2.5 (May 4th 2011)
    - bug #5 corrected: program could run indefinitely when "-t" option value was
    set too high.
    - new option "-i" to improve the coverage of long n-grams, by generalizing
    the indexation phase to n-grams rather than simple words. Default value is 1,
    which corresponds to the original behavior. The larger, the more n-grams output,
    but the slower the program and the more memory required at startup. To be
    improved...
    - replaced "-v" option (verbose) with "-q" (quiet). Default behavior is now
    verbose. Also, now displays the average size of subcorpora processed in addition
    to the number of subcorpora (info is now persistent).
    - changed default value for "-N" option from 0 (no limit) to 7.
    - set a limit on the size of subcorpora processed (100,000 sentences, hard
    coded). This prevents the program from spending too much time on huge (though
    rare) subcorpora, giving an impression of hanging.
    
    2.4 (September 29th 2010)
    - bug #4 corrected: hash collisions could make the program crash randomly when
    computing translation probabilities.
    - corrected inconsistency in long option names: "--min-gram" -> "--min-ngram".
    
    2.3 (July 20th 2009)
    - bug #3 corrected: under some conditions, computing lexical weights could make
    the program crash.
    - changed the "-n" and "-N" option behavior: now filter out alignments that
    contain ANY n-gram that does not verify the specified length constraints
    (formerly ONLY).
    
    2.2 (June 9th 2009)
    first public release
    
    
    ===============================================================================
    
    List of nice people who helped in some way (hints, requests, bugs), starting
    from former malign.py:
    
    Yves Lepage
    Julien Gosme
    Francis Bond
    Alex Yanishevsky
    Sue Chen
    Jonathan Chevelu
    Aurélien Max
    François Yvon
    Kota Takeya
