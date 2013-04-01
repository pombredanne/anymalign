# HOW **anymalign** works

1.  load `N` lines of multi-lang corpura.

2.  randomly take a subcorpura of `k` lines by sampling.

                                               C
        p( size_of_subcorpura = k ) = --------------------
                                       k * ln( 1 - k / N)

    each line is *equal* in sampling.

    suppose we took a subcorpura of 3 lines from bilingual data.

        a1 a2 a3  | b1 b2
           a2 a3  |    b2
        a1        | b1 b2

3.  scan subcorpura and obtain a dictionary `{ word : [ line it occured in ] }`

        {
            a1 : [1,3]       ,
            a2 : [1,2]       ,
            a3 : [1,2]       ,
            b1 : [1,3]       ,
            b2 : [1,2,3]     ,
        }

4.  reverse the dictionary in step2, getting `{ [ lineId] : { word } } `

        {
            [1,2]  : { a2, a3 } ,
            [1,3]  : { a1, b1 } ,
            [1,2,3]: { b2 }     ,
        }

    *note* : with `-i` switch, #3-4 would be slightly different.

5.  - for each set of lines, and its corresponding `wordSet` :  ( `{ [1,3]  : { a1, b1 } }` )
    - for each line in set: ( `line 1` )
    - for each word in the line

      if word is in `wordSet`, add word to `perfect phrase`

      else, add word to `complementary phrase`

      → `perfect phrase` : `a1 <=> b1`

      → `complementary phrase` : `a2,a3 <=> b2`

      are 2 alignments we found.
