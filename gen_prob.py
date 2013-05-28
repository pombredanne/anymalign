#!/usr/bin/env python2
# encoding: utf-8

import argparse

from sys import stdout, stderr
from operator import add
from collections import defaultdict
from pprint import pprint
import math

def parse_cmd():
    p = argparse.ArgumentParser()
    p.add_argument("test_corpus",
            nargs="+",
            help="tokenized test corpus in source language, to bias toward")
    p.add_argument("-s", "--source",
            required=True,
            help="tokenized monolignaul source corpus"
            )
    p.add_argument("-t", "--target",
            required=True,
            help="tokenized monolignaul target corpus"
            )
    p.add_argument("-o", "--output",
            help="output file. print to stdout if not specified."
            )
    p.add_argument("-b", "--bias",
            required=True,
            help="bias function"
            )
    p.add_argument("-d", "--debug",
            action="store_true",
            help="print debug info to stdout or the file specified by -o"
            )
    return p.parse_args()

class Bias(object):
    """Give sampling probabilities to train corpus"""
    def __init__(self, source_sentences, target_sentences, test_sentences ):
        """
        :source_sentences: list of str
        :target_sentences: list of str
        :test_sentences: list of str
        """
        self.corpus = {
                "source" : tuple(line.split() for line in source_sentences ),
                "target" : tuple(line.split() for line in target_sentences ),
                "test"   : tuple(line.split() for line in test_sentences ),
                }

        self.word_freq = {
                k : self.calculate_word_freq(v)
                for k,v in self.corpus.iteritems()
                }

        self.word_occ = {
                k : self.calculate_word_occ(v)
                for k,v in self.corpus.iteritems()
                }

    def calculate_word_freq(self, lines):
        # absolute frequency for words
        ret = defaultdict(int)
        for line in lines:
            for word in line:
                ret[word] += 1
        return ret

    def calculate_word_occ( self, lines):
        # lines occured in , for words
        ret = defaultdict(set)
        for lineNo in range(len(lines)):
            for word in lines[lineNo]:
                ret[word].add(lineNo)
        return ret

    def prob_of_line( self, lineNo):
        raise NotImplementedError()

    def run(self):
        raise NotImplementedError()

    def output(self, out):
        for lineNo in range( len(self.corpus["source"] ) ):
            out.write( "%.40e\n" % (self.prob_of_line(lineNo) ) )

    def dump(self, out=None):
        dump = {
            "corpus" : self.corpus,
            "word_freq" : self.word_freq,
            "word_occ" : self.word_occ,
            }
        if out:
            pprint( dump, stream = out )
        return dump

    def idf_score(self, key ):
        # key : source | target | test
        # return { word : idf_score(word) }
        num_lines = float( len(self.corpus[ key ]) )
        word_occ  = self.word_occ[ key ]
        ret = {}
        for word, docs in word_occ.iteritems():
            idf = math.log( num_lines / len(docs) )
            ret[word] = idf
        return ret

class FairBias(Bias):
    def run(self):
        pass
    def prob_of_line( self, lineNo ):
        return 1

class SplitIDF1(Bias):
    def run(self):
        # XXX what about other informativeness score, like entropy 
        idf_source = self.idf_score( "source" )
        idf_target = self.idf_score( "target" )
        test_words = self.word_occ[ "test" ]

        # pass1 : weight lines on source side
        # for each source sentence [Ws] in training corpus 
        # w = sum( [ idf(W) if W occured in test set ] )
        # idf is calculated within source corpus
        weight_pass1 = defaultdict(float) # line_no : weight
        for line_no, source_sentence in enumerate( self.corpus[ "source" ] ):
        # XXX should line be converted to set?
            for word in set(source_sentence):
        # XXX for word not appered in test set, should its idf score be discarded?
                if word in test_words:
                    weight_pass1[line_no] += idf_source[word]

        # convert weight_pass1( weight of lines) to weight_target_words( weight of words )
        # by splitting weight_pass1[line] to target words in aligned sentence,
        # in proportion to their idf score in target corpus
        weight_target_words_multi = defaultdict(list) # word : [list of weights]
        for line_no, target_sentence in enumerate( self.corpus[ "target" ] ):
            sum_target_idf  = sum( idf_target[word] for word in target_sentence )
            for word in target_sentence:
                weight_target_words_multi[word].append( weight_pass1[line_no] * idf_target[word] / sum_target_idf )
        weight_target_words = {
                # XXX what to do with possible weights, except mean ?
                word : sum(weights)/len(weights)
                for word,weights in weight_target_words_multi.iteritems()
                }

        # pass2 : weight lines on target side, which is final score
        # weight of line :: sum( weight_target_words[] )
        weight_pass2 = defaultdict(float)
        for line_no, target_sentence in enumerate( self.corpus[ "target" ] ):
            for word in target_sentence:
                weight_pass2[ line_no ] += weight_target_words[ word ]

        self.__weight_pass1 = weight_pass1
        self.__idf_score = {
                "source" : idf_source,
                "target" : idf_target,
                }
        self.__weight_target_words_multi = weight_target_words_multi
        self.__weight_target_words = weight_target_words
        self.__weight_pass2 = weight_pass2

    def prob_of_line( self, line_no ):
        return self.__weight_pass2[ line_no ]

    def dump( self, out=None ):
        ret = Bias.dump(self)
        ret.update( {
            "weight_pass1" : self.__weight_pass1,
            "weight_pass2" : self.__weight_pass2,
            "weight_target_words_multi" : self.__weight_target_words_multi,
            "weight_target_words" : self.__weight_target_words,
            "idf" : self.__idf_score,
            })
        if out:
            pprint( ret, stream=out )
        return ret

def BiasFactory(bias_type, *args):
    klass_table = {
            "fair" : FairBias,
            "split_idf1" : SplitIDF1
            }

    if bias_type in klass_table:
        return klass_table[bias_type](*args)
    else:
        raise ValueError(
                "invalid bias type <%s>, expected one of %s"%
                ( bias_type, str(klass_table.keys() ) )
                )

def read_monolingual_corpus(filename):
    lines = open(filename).readlines()
    return lines

def read_bilingual_corpus(filename):
    lines = open(filename).readlines()
    source_sentences = list(line.split("\t")[0] for line in lines)
    target_sentences = list(line.split("\t")[1] for line in lines)
    return source_sentences, target_sentences

def main():
    args = parse_cmd()
    source_sentences = read_monolingual_corpus( args.source )
    target_sentences = read_monolingual_corpus( args.target )
    test_sentences = reduce( add, map(read_monolingual_corpus, args.test_corpus ) )

    assert( len(source_sentences) == len(target_sentences) )

    stderr.write( "%i x2 sentences in train corpus\n"%( len(source_sentences) ) )
    stderr.write( "%i sentences in test corpus\n"%( len(test_sentences) ) )

    biaser = BiasFactory( args.bias, source_sentences, target_sentences, test_sentences )
    biaser.run()

    if args.output:
        out = open(args.output, "w")
    else:
        out = stdout

    if args.debug:
        biaser.dump(out)
    else:
        biaser.output(out)

if __name__ == "__main__":
    main()
