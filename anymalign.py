#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2008, 2009, 2010, 2011 Adrien Lardilleux
# <Adrien.Lardilleux@limsi.fr>
# http://users.info.unicaen.fr/~alardill/anymalign/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Multilingual aligner.

Requires Python version 2.x (x >= 4).

"""

import os
import sys
import optparse
from time import time

import bz2
import gzip
from xml.sax.saxutils import escape
from tempfile import NamedTemporaryFile

import math
import random
from array import array
from operator import mul
from bisect import bisect_left


__version__ = '2.5 (May 4th 2011)'
__author__ = 'Adrien Lardilleux <Adrien.Lardilleux@limsi.fr>'
__scriptName__ = 'anymalign'
__verbose__ = False
__tmpDir__ = None

MAX_SUBCORPUS_SIZE = 100000

###############################################################################
# Utility functions
###############################################################################

def parse_field_numbers(fields, maxFields):
    """Get a set of integers from a command line option.

    -- fields: str
    -- maxFields: int

    <fields> has the same format as the Unix cut(1)'s -f option value:
    comma-separated list of integers, starting from 1. A run of integers can
    be specified by a dash. A set of integers is returned. <maxFields> is the
    total number of columns (number of languages). Raise ValueError if
    <fields> is not well formed.

    >>> parse_field_numbers("1,4", 5)
    set([1, 4])
    >>> parse_field_numbers("-3,6-", 8)
    set([1, 2, 3, 6, 7, 8])
    >>> parse_field_numbers("-", 3)
    set([1, 2, 3])
    
    """
    selection = set()
    for f in fields.split(','):
        if not f:
            continue
        start_end = f.split('-')
        if len(start_end) > 2:
            raise ValueError
        elif len(start_end) == 1 and start_end[0]:
            selection.add(int(start_end[0]))
        else:
            start, end = start_end
            if start:
                start = int(start)
            else:
                start = 1
            if end:
                end = int(end)
            else:
                end = maxFields
            selection.update(xrange(start, end + 1))
    return selection



def make_temp_file(suf=''):
    """Return a new temporary file.

    -- suf: str

    Convenience function to create temporary files using the global __tmpDir__
    and __scriptName__ (file name prefix) variables. <suf> is appended to the
    end of the filename. The tempfile module is used.
    
    """
    return NamedTemporaryFile(dir=__tmpDir__, prefix=__scriptName__,
                              suffix=suf)

def open_compressed(filename):
    """Open a file for reading, based on its name.

    -- filename: str

    Call the appropriate module (gz, bz2), based on the filename extension,
    and return a file-like object opened for reading.
    
    """
    if filename.endswith('.gz'):
        return gzip.open(filename, 'rb')
    elif filename.endswith('.bz2'):
        return bz2.BZ2File(filename, 'r')
    else:
        return open(filename, 'rb')
    

def message(msg, out=sys.stderr):
    """Send some info into the specified file.

    -- msg: str
    -- out: file

    Nothing is written if the global variable  __verbose__ is False.
    
    """
    if __verbose__:
        out.write(str(msg))

def optimum_array(initialList, maxi=None):
    """Return a memory-efficient copy of a list of integers.

    -- initialList: list(int)
    -- maxi: int

    An array.array is returned, using the smallest possible number of bytes
    for representing numbers, based on <initialList>'s maximum. If <maxi> is
    specified, it is used as the maximum of the list (faster). A tuple is
    returned if no array can fit.

    >>> optimum_array([255])
    array('B', [255])
    >>> optimum_array([255, 256])
    array('H', [255, 256])

    """
    if maxi is None:
        maxi = max(initialList)
    for typecode in "BHiIlL":
        try:
            array(typecode, [maxi])
        except OverflowError:
            pass
        else:
            return array(typecode, initialList)
    return tuple(initialList)


class CoocDB:
    """Container for word cooccurrence counts.

    -- self.pairs: list(array.array)
        For a given source word i, self.pairs[i] contains an ordered array
        which elements are the target words with which i cooccurs.
    -- self.freqs: list(array.array)
        Same as self.pairs, but contains the corresponding frequencies
        (len(self.freqs) = len(self.pairs) = number of source words).

    Searching for some word cooccurrence frequency implies:
    - a random access for the source word;
    - a dichotomy for the target word;
    - a random access for the frequency.

    [Other possibilities:    
    - all in memory with dictionaries: the fastest, but requires too much
    memory;
    - computing word cooccurrence frequencies on the fly: too slow;
    - storing counts on disk, using sqlite: too slow on large data.]

    >>> db = CoocDB(3)
    >>> db.add(1, {3:2, 4:5})
    >>> db.get(1, 4)
    5
    
    """
    def __init__(self, nbWords):
        """Initializer.

        -- nbWords: int
            Number of source words.
        """
        self.pairs = [None] * nbWords
        self.freqs = [None] * nbWords
    
    def add(self, sourceWord, cooc):
        """Add cooccurrence counts for a new source word.

        -- sourceWord: int
            The source word id.
        -- cooc: dict(int:int)
            Mapping between target word ids (keys) and frequencies (values).
        """
        targets = sorted(cooc)
        self.pairs[sourceWord] = optimum_array(targets, targets[-1])
        self.freqs[sourceWord] = optimum_array([cooc[tw] for tw in targets])
    
    def get(self, sourceWord, targetWord):
        """Retrieve cooccurrence count between a source and a target word.

        -- sourceWord: int
            The source word id.
        -- targetWord: int
            The target word id.
        """
        return self.freqs[sourceWord][bisect_left(self.pairs[sourceWord],
                                                  targetWord)]


class Progression:
    """Display progress percentage.

    -- self.step: float
        Base value to be added at each update.
    -- self.progress: float
        Current percentage, between 0. and 100.
    -- self.lastWrite: float
        The last displayed value.
    """
    
    def __init__(self, maxi):
        """Initializer.

        -- maxi: int
            Number of expected updates.
        """
        self.step = 100. / maxi
        self.progress = 0.
        self.lastWrite = -1
    
    def next(self, val=1):
        """Increase percentage and refresh display if needed.

        -- val: int
            Number of actual updates to be performed.
        """
        self.progress += val * self.step
        newWrite = int(round(self.progress))
        if newWrite != self.lastWrite:
            self.lastWrite = newWrite
            message("\r%3i%%" % newWrite)


class Distribution:
    """Generate random integers according to a specific function.

    -- self.values: array.array('f')
    -- self.start: int
        Lower bound of definition interval.
    -- self.nbVal: int
        Number of values to be stored = len(self.values)
    """
    
    def __init__(self, function, start, end):
        """Initializer.

        -- function: function
            1-argument function. <function>(x) will be proportional to the
            probability that the integer x be chosen.
        -- start: int
            = self.start
        -- end: int
            Upper bound of definition interval.
        """
        values = [function(x) for x in xrange(start, end + 1)]
        fact = 1. / sum(values)
        s = 0.
        for i, v in enumerate(values):
            s += fact * v
            values[i] = s
        self.values = array('f', values)
        self.start = start
        self.nbVal = end + 1 - start
    
    def next(self):
        """Return new random integer, according to distribution."""
        r = random.random()
        values = self.values
        i = -1
        for i in xrange(self.nbVal):
            if r < values[i]:
                return self.start + i
        return self.start + i    # We should never reach this line


###############################################################################
# Output formatters
###############################################################################

class PlainWriter:
    """Output alignments in plain text format.

    -- self.outputFile: file
        Where alignments have to be written.
    """
    
    def __init__(self, outputFile):
        """Initializer.

        -- outputFile: file
            = self.outputFile
        """
        self.outputFile = outputFile
    
    def write(self, line):
        """Write new alignment as it is (do not modify anything).

        -- line: str
            The alignment to be written.
        """
        self.outputFile.write(line)
    
    def terminate(self):
        """Terminates writing."""
        self.outputFile.flush()


class MosesWriter(PlainWriter):
    """Output alignments in a format suitable for the Moses decoder."""
    
    def write(self, line):
        """Write new alignment.

        -- line: str
            The alignment to be written.

        - Replace tabs between languages by " ||| ";
        - scores are separated by spaces, in a single field;
        - add exp(1) at the end of scores.
        """
        alignment, lexWeights, probas, _ = line.rsplit('\t', 3)
        # Remove lexical weights if necessary
        try:
            for f in lexWeights.split():
                float(f)
        except ValueError:
            lexWeights = ""
        else:
            lexWeights = " " + lexWeights
        self.outputFile.write("%s |||%s %s 2.718\n" %
                              (alignment.replace('\t', ' ||| '),
                               lexWeights, probas))


class HTMLWriter:
    """Output alignments in XHTML.

    -- self.outputFile: file
        Where alignments have to be written.
    -- self.inputEncoding: str
        Encoding of incoming data.
    -- self.langList: str
        Comma-separated list of languages (languages can be anything).
    -- self.counter: int
        Current alignment number.
    -- self.maxFreq: int
        Frequency of the most frequent alignment (i.e. the first one).
    """
    
    def __init__(self, outputFile, inputEncoding, langList):
        """Initializerr.

        -- outputFile: file
            = self.outputFile
        -- inputEncoding: str
            = self.inputEncoding
        -- langList: str
            = self.langList

        Also outputs the HTML header.
        
        """
        if langList is None:
            langList = []
        else:
            langList = langList.split(',')
        self.counter = 1
        self.maxFreq = None
        self.outputFile = outputFile
        outputFile.write('''<?xml version="1.0" encoding="%s"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">\n<head>
<meta http-equiv="content-type" content="text/html; charset=%s" />
<title>anymalign.py: output</title>
<style type="text/css">
 td { border: solid thin rgb(224,224,224); padding: 5px; text-align: center }
 td.n { font-family: monospace; text-align: right }
 th { background-color: rgb(240, 240, 240); border: thin outset }
</style>\n</head>
<body>\n<table cellspacing="0pt">
<tr>\n <th>No</th>\n <th>Freq.</th>\n <th>Translation<br/>probabilities</th>
 <th>Lexical<br/>weights</th>\n%s</tr>\n''' % (
     inputEncoding, inputEncoding,
     "".join([" <th>%s</th>\n" % l for l in langList])))

    def write(self, line):
        """Write new alignment.

        -- line: str
            The alignment to be written.

        - Alignment is wrapped in a table row;
        - scores are displayed first, preceded by alignment counter.
        """
        alignment = line.split('\t')
        freq = int(alignment.pop())
        probas = [float(p) for p in alignment.pop().split()]
        lexWeights = alignment.pop()
        try:
            lexWeights = [float(lw) for lw in lexWeights.split()]
        except ValueError:
            blue = 256
        else:
            blue = 128 + 128 * (1 - reduce(mul, lexWeights, 1.) ** (1./len(lexWeights)))
            lexWeights = "&nbsp;".join(["%.2f" % lw for lw in lexWeights])
        if self.maxFreq is None:
            self.maxFreq = math.log(freq)
        red = 255. * (1. - math.log(freq) / self.maxFreq)
        green = 255 * (1 - reduce(mul, probas, 1.) ** (1./len(probas)))
        self.outputFile.write(
            """<tr>\n <td class="n">%i</td>
 <td class="n" style="background-color:rgb(255,%i,%i)">%i</td>
 <td class="n" style="background-color:rgb(%i,255,%i)">%s</td>
 <td class="n" style="background-color:rgb(%i,%i,255)">%s</td>
%s</tr>\n""" % (self.counter, red, red, freq, green, green,
                "&nbsp;".join(["%.2f" % p for p in probas]), blue, blue,
                lexWeights,
                "".join([" <td>%s</td>\n" % escape(cell)
                         for cell in alignment])))
        self.counter += 1

    def terminate(self):
        """Terminates writing (close HTML tags)."""
        self.outputFile.write("</table>\n</body>\n</html>\n")
        self.outputFile.flush()

class TMXWriter:
    """Output alignments in XML (TMX).

    -- self.outputFile: file
        Where alignments have to be written.
    -- self.inputEncoding: str
        Encoding of incoming data.
    -- self.langList: str
        Comma-separated list of languages (languages can be anything).
    -- self.nbLanguages: int
        Number of languages in alignments.
    """
    
    def __init__(self, outputFile, inputEncoding, langList):
        """Initializer.

        -- outputFile: file
            = self.outputFile
        -- inputEncoding: str
            = self.inputEncoding
        -- langList: str
            = self.langList

        This also outputs the XML header.
        """
        self.inputEncoding = inputEncoding
        self.outputFile = outputFile
        if langList is None:
            self.langList = []
        else:
            self.langList = langList.split(',')
        self.nbLanguages = len(self.langList)
        outputFile.write('''<?xml version="1.0"?>
<tmx version="1.4">
<header creationtool="%s" creationtoolversion="%s" datatype="plaintext"
 segtype="phrase" adminlang="en-us" srclang="*all*" o-tmf="none" />
<body>\n''' % (__scriptName__, __version__))

    def write(self, line):
        """Write new alignment.

        -- line: str
            The alignment to be written.

        - Alignment is wrapped in translation unit <tu>;
        - one variant <tuv> per language;
        - scores are included in <prop> tags.
        """
        alignment = line.split('\t')
        freq = alignment.pop().rstrip('\n')
        probas = alignment.pop()
        lexWeights = alignment.pop()
        langList = self.langList + \
                   ["_lang%i_" % i
                    for i in xrange(self.nbLanguages + 1,
                                    len(alignment) + 1)]
        self.outputFile.write(
            '<tu>\n <prop type="freq">%s</prop>\n'
            ' <prop type="probas">%s</prop>\n'
            ' <prop type="lexWeights">%s</prop>\n%s</tu>\n' %
            (freq, probas, lexWeights,
             ''.join([' <tuv xml:lang="%s"><seg>%s</seg></tuv>\n' %
                      (lang,
                       escape(phrase).decode(self.inputEncoding).encode(
                           'ascii', 'xmlcharrefreplace'))
                      for lang, phrase in zip(langList, alignment)])))

    def terminate(self):
        """Terminates writing (close XML tags)."""
        self.outputFile.write("</body>\n</tmx>\n")
        self.outputFile.flush()


###############################################################################
# Function shared by Aligner class and merge() function
###############################################################################

def set_proba(inputFile, inputDict, writer):
    """Update probabilities in alignment file.

    -- inputFile: file
        Contains alignments, tab-separated languages + lexical
        weights in last field.
    -- inputDict: dict(int: dict(int: int))
        Absolute frequencies of alignments. Keys are alignment lengths (number
        of bytes), values are dictionaries which keys are alignment hashes and
        values are integer frequencies.
    -- writer: {Plain,Moses,HTML,TMX}Writer
    """
    nbAlignments = 0
    # Sort: read inputFile once to determine where each line begins
    offsetsByFreq = {}
    inputFile.seek(0)
    offset = 0
    for line in inputFile:
        nbAlignments += 1
        alignment = line.rsplit('\t', 1)[0] # Remove lexical weights
        freq = inputDict[len(alignment)][hash(alignment)]
        offsetsByFreq.setdefault(freq, []).append(offset)
        offset += len(line)
    inputDict.clear()   # Release memory
    
    message("\r%i alignments\n" % nbAlignments)
    if not nbAlignments:
        return

    # Read inputFile once more, according to absolute frequencies, and
    # dump everything into compressed file
    message("Sorting alignments\n")
    nextPercentage = Progression(nbAlignments).next
    tmpFile = make_temp_file(".al_lw.gz")
    compressedFile = gzip.GzipFile(fileobj=tmpFile, mode="wb", compresslevel=1)
    try:
        alNo = 0
        for freq in sorted(offsetsByFreq.iterkeys(), reverse=True):
            for offset in offsetsByFreq.pop(freq):
                alNo += 1
                inputFile.seek(offset)
                print >> compressedFile, "%s\t%x" % \
                      (inputFile.readline().rstrip('\n'), freq)
                nextPercentage()
        compressedFile.close()
        inputFile.close()   # Delete temporary input file
        offsetsByFreq.clear()

        message("\rComputing conditional probabilities...\n")
        nextPercentage = Progression(nbAlignments).next
        tmpFile.seek(0)
        compressedFile = gzip.GzipFile(fileobj=tmpFile, mode="rb")
        # Count the number of occurrences of all parts of alignments
        nbLanguages, nbSplits = None, None
        for line in compressedFile:
            if nbLanguages is None:
                nbSplits = line.count('\t')
                nbLanguages = nbSplits - 1
                phraseFreq = [{} for _ in xrange(nbLanguages)]
            alignment = line.split('\t', nbSplits)
            freq = int(alignment.pop(), 16)
            alignment.pop() # Remove lexical weights
            for phrase, counts in zip(alignment, phraseFreq):
                phraseHash = hash(phrase)
                counts[phraseHash] = counts.get(phraseHash, 0) + freq
            nextPercentage()
        compressedFile.close()
        
        # Output alignments
        tmpFile.seek(0)
        compressedFile = gzip.GzipFile(fileobj=tmpFile, mode="rb")
        message("\rOutputting results...\n")
        nextPercentage = Progression(nbAlignments).next
        nbSplits = nbLanguages
        try:
            for line in compressedFile:
                alignmentStr, lexWeights, freq = line.rsplit('\t', 2)
                alignment = alignmentStr.split('\t', nbSplits)
                freq = int(freq, 16)
                probas = ' '.join(["%f" % (1. * freq / counts[hash(phrase)])
                                   for phrase, counts
                                   in zip(alignment, phraseFreq)])
                writer.write("%s\t%s\t%s\t%i\n" % (alignmentStr, lexWeights,
                                                   probas, freq))
                nextPercentage()
            writer.terminate()
        except IOError:
            pass
        message("\r")
    finally:
        tmpFile.close()


###############################################################################
# Merge alignment files
###############################################################################

def merge(inputFilenames, writer):
    """Merge alignments from several input files.

    -- inputFilenames: list(str)
        List of file names from which alignments have to be merged.
        Standard input is refered to as "-".
    -- writer: {Plain,Moses,HTML,TMX}Writer

    An incoming alignment is assumed to be formatted as <alignment> <tab>
    <lexicalWeights> <tab> <translationProbabilities> <TAB> <integer>
    <EOL>. No check is performed, and any number of tabs may occur in
    <alignment>. <alignment> is unchanged. If identical alignments with
    different <lexicalWeights> are input, only lexical weights from the
    first alignment are kept.

    To save memory, <alignment>s are dumped in a sequential file. Only the
    association between <alignment>s' hash values and their frequencies are
    kept in memory in a dictionary. Thus we assume that two <alignment>s with
    the same hash value are equal. This is basically wrong, but we have plenty
    of possible hashes before a collision occurs.

    The output format is the same as input. <alignment>s are guaranteed to be
    unique and are sent to <outputFile>, sorted according to the <integer>
    field in decreasing order. The <translationProbabilities> are updated
    accordingly (one float per language).
    
    """
    files = []
    counts = {} # Absolute frequencies of alignments
    weightedAlignmentFile = make_temp_file('.al_lw')
    try:
        for f in inputFilenames:
            if f == "-":
                files.append(sys.stdin)
            else:
                files.append(open_compressed(f))
        # Sum up absolute frequencies for alignments
        for inputFile in files:
            for line in inputFile:
                alignment_lw, _, freq = line.rsplit('\t', 2)
                alignment = alignment_lw.rsplit('\t', 1)[0]
                bucket = counts.setdefault(len(alignment), {})
                alignmentHash = hash(alignment)
                previousFreq = bucket.get(alignmentHash)
                if previousFreq is None:
                    bucket[alignmentHash] = int(freq)
                    print >> weightedAlignmentFile, alignment_lw
                else:
                    bucket[alignmentHash] = previousFreq + int(freq)
        
        weightedAlignmentFile.seek(0)
        set_proba(weightedAlignmentFile, counts, writer)
    finally:
        weightedAlignmentFile.close()
        for f in files:
            f.close()
    

    
###############################################################################
# Alignment mode
###############################################################################

class Aligner:
    """Generate word alignments from sentence-aligned corpora.

    -- self.files: list(file)
        Input files, open for reading.
    -- self.offsets: list(array.array(int))
        For each file (corresponding indices in self.files), the list of
        positions of start of lines.
    -- self.nbLanguages: int
        Number of languages in the corpus.
    -- self.corpus: list(lit(int))
        The corpus is a list of lines.
        A line is a list of integers (1 integer = 1 word).
    -- self.allWords: list(str)
        Vocabulary from the corpus. Word ids in self.corpus correspond to
        position indices in self.allWords. Words are sorted by frequency, most
        frequent first (smallest id). The first word is special and contains
        the discontinuity delimiter.
    -- self.wordFreq: array.array(int)
        Frequencies associated to self.allWords: len(self.allWords) =
        len(self.wordFreq). The first frequency is a dummy one because it
        corresponds to the discontiguity delimiter, and is always set to the
        highest "actual" frequency + 1 (self.wordFreq[0] = self.wordFreq[1] +
        1).
    -- self.wordLanguages: array.array(int)
        Languages all words are from: len(self.allWords) =
        len(self.wordLanguages). Languages are 0-based.
        max(self.wordLanguages) = self.nbLanguages - 1
    -- self.counts: dict(int: dict(int: int))
        Same as <inputDict> argument of set_proba() function.
    -- self.nbAlignments: int
        Total number of alignments = sum(len(c) for c in self.counts).
    -- self.weightedAlignmentFile: file
        Same as <inputFile> argument of set_proba() function.
        Number of lines in this file equals self.nbAlignments.
    -- self.minLanguages: int
        The "-l" command line option value.
    -- self.minSize: int
        The "-n" command line option value.
    -- self.maxSize: int
        The "-N" command line option value.
    -- self.delimiter: str
        The "-d" command line option value, or None.
    -- self.indexN: int
        The "-i" command line option value.
    -- self.contiguousFields: list(bool)
        For each language, a bool indicates whether only contiguous words
        should be output or not. len(self.contiguousFields) = self.nbLanguages
    -- self.weightFunc: function
        {self._dummy_weight|self._lexical_weight}, according to
        "-w" command line flag.

    Main process is as follows:
    1) Read all input files, keep only line start offsets in memory;
    2) sample (no replacement) line offsets, load corresponding lines into
    memory;
    3) extract all possible alignments from subcorpus in memory (sample with
    replacement), output alignments in temporary file (contains word ids, not
    actual words);
    4) dump temporary file into main alignment file
    (self.weightedAlignmentFile), after replacing word ids by actual strings
    and adding lexical weights if requested;
    5) repeat steps 2-4 until all input corpus is consumed;
    6) pass main alignment file to set_proba() function to add translation
    probabilities and format output.
    
    """

    def __init__(self, inputFilenames, writer, nbNewAlignments, maxNbLines,
                 timeout, doLexWeight, discontiguousFields, minLanguages,
                 minSize, maxSize, delimiter, indexN):
        """Initializer.

        Main process is coded in initializer. That's not very clean, but
        simpler.

        -- inputFilenames: list(str)
            Filenames specified on acommand line. Can contain standard input
            "-". If so, stdin is dumped into a temporary file to permits
            random line access.
        -- writer: {Plain,Moses,HTML,TMX}Writer
        -- nbNewAlignments: int
            The "-a" command line option value.
        -- maxNbLines: int
            The "-S" command line option value.
        -- timeout: float
            The "-t" command line option value.
        -- doLexWeight: bool
            Indicates whether lexical weights computation is requested.
        -- discontiguousFileds: str
            The "-D" command line option value.
        -- minLanguages: int
            The "-l" command line option value.
        -- minSize: int
            The "-n" command line option value.
        -- maxSize: int
            The "-N" command line option value.
        -- delimiter: str
            The "-d" command line option value.
        -- indexN: int
            The "-i" command line option value.
        """
        self.minSize = minSize
        self.maxSize = maxSize
        if delimiter:
            self.delimiter = delimiter
        else:
            self.delimiter = None
        self.indexN = max(indexN, 1)
        if doLexWeight:
            self.weightFunc = self._lexical_weight
        else:
            self.weightFunc = self._dummy_weight
        self.counts = {}
        self.nbAlignments = 0   # = sum(len(c) for c in self.counts)
        self.files = []
        self.weightedAlignmentFile = make_temp_file(".al_lw")
        try:
            for f in inputFilenames:
                if f == "-":
                    inFile = make_temp_file(".stdin")
                    inFile.writelines(sys.stdin)
                    inFile.seek(0)
                    self.files.append(inFile)
                else:
                    self.files.append(open_compressed(f))
            self.offsets = []
            nbLines = None
            self.nbLanguages = 0
            for f in self.files:
                offset = 0
                fileOffsets = []
                fileLanguages = None
                lineId = -1
                for lineId, line in enumerate(f):
                    fl = line.count('\t') + 1
                    if fileLanguages is None:
                        fileLanguages = fl
                        self.nbLanguages += fl
                    else:
                        assert fl == fileLanguages, "Found %i columns " \
                               " instead of %i at line %i in file %s" % \
                               (fl, fileLanguages, lineId + 1, f.name)
                    fileOffsets.append(offset)
                    offset += len(line)
                if nbLines is None:
                    nbLines = lineId + 1
                else:
                    assert nbLines == lineId + 1, \
                           "Input files have different number of lines"
                self.offsets.append(optimum_array(fileOffsets))
                del fileOffsets
            message("Input corpus: %i languages, %i lines\n" %
                    (self.nbLanguages, nbLines))
            
            if minLanguages is None:
                self.minLanguages = self.nbLanguages
            else:
                self.minLanguages = minLanguages

            ncf = parse_field_numbers(discontiguousFields, self.nbLanguages)
            self.contiguousFields = [(i + 1 not in ncf)
                                     for i in xrange(self.nbLanguages)]

            if timeout < 0:
                timeout = None

            if maxNbLines < 1:
                nbCorpora = 1
            else:
                nbCorpora = int(math.ceil(1. * nbLines / maxNbLines))
                message("Split input corpus into %i subcorpora" % nbCorpora)
                if timeout is not None:
                    timeout /= 1. * nbCorpora
                    message(" (timeout: %.2fs each)" % timeout)
                message("\n")
            lines = range(nbLines)
            random.shuffle(lines)
            for nbCorpToDo in xrange(nbCorpora, 0, -1):
                if nbCorpora > 1:
                    message("\r%i subcorpora remaining\n" % nbCorpToDo)
                selection = [lines.pop() for _ in
                             xrange(int(math.ceil(1. * len(lines) /
                                                  nbCorpToDo)))]
                selection.sort()    # Speed up disk access
                self.set_corpus(selection)
                self.run(timeout, nbNewAlignments)
            set_proba(self.weightedAlignmentFile, self.counts, writer)
        finally:
            self.weightedAlignmentFile.close()
            for f in self.files:
                f.close()

        

    def set_corpus(self, lines):
        """Load subcorpus into memory.

        -- lines: list(int)
            The line numbers. These are indices of arrays in self.offsets.
        """
        self.corpus = [[] for _ in lines]
        self.allWords, self.wordLanguages = [], []
        allWordIds = [{} for _ in xrange(self.nbLanguages)]
        nbLanguagesDone = 0
        # Read files sequentially, rather than in parallel (faster)
        for f, fileOffsets in zip(self.files, self.offsets):
            for lineId, offsetId in enumerate(lines):
                f.seek(fileOffsets[offsetId])
                line = self.corpus[lineId]
                for i, sentence in enumerate(f.readline().split('\t')):
                    languageId = i + nbLanguagesDone
                    wordIds = allWordIds[languageId]
                    for word in sentence.split():
                        wordId = wordIds.get(word)
                        if wordId is None:
                            wordId = len(self.allWords)
                            wordIds[word] = wordId
                            self.allWords.append(word)
                            self.wordLanguages.append(languageId)
                        line.append(wordId)
            nbLanguagesDone = languageId + 1

        # Compute word frequencies
        self.wordFreq = [0] * len(self.allWords)
        for line in self.corpus:
            for wordId in set(line):
                self.wordFreq[wordId] += 1

        # Add discontinuity delimiter
        self.allWords.append(self.delimiter)
        self.wordLanguages.append(self.nbLanguages)
        self.wordFreq.append(max(self.wordFreq) + 1)
        
        # Reassign word ids: smallest id for most frequent word
        sortedByFreq = sorted(xrange(len(self.allWords)),
                              key=self.wordFreq.__getitem__, reverse=True)
        self.allWords = [self.allWords[i] for i in sortedByFreq]
        self.wordLanguages = optimum_array([self.wordLanguages[i]
                                            for i in sortedByFreq],
                                           self.nbLanguages)
        newPos = [None] * len(self.allWords)
        for i, wordId in enumerate(sortedByFreq):
            newPos[wordId] = i
        for i, line in enumerate(self.corpus): # Replace word ids in corpus
            self.corpus[i] = [newPos[wordId] for wordId in line]
        
        self.wordFreq.sort(reverse=True)
        self.wordFreq = optimum_array(self.wordFreq)

        ### new with -i option ###
        # Store multiple n-gram-ized copies of the corpus to speed up
        # subsequent alignment phase. That's memory intensive, but
        # sooo much faster than retrieving n-grams from words every
        # time a sub-corpus is processed. The program would need a
        # complete rewriting to handle this properly, as Anymalign was
        # first designed to process only words.

        ngramRange = range(2, self.indexN + 1)
        languageRange = range(self.nbLanguages)

        allNgramIds = [{} for _ in ngramRange]
        self.allNgrams = [[] for _ in ngramRange]
        self.ngramCorpora = [[] for _ in ngramRange]
        
        for line in self.corpus:
            sentences = [[] for _ in languageRange]
            ngramSentences = [set() for _ in ngramRange]
            for word in line:
                sentences[self.wordLanguages[word]].append(word)
            for s in sentences:
                s = tuple(s)
                lastIdx = len(s) + 1
                for n in xrange(2, min(self.indexN+1, lastIdx)):
                    ngramIds = allNgramIds[n-2]
                    ngrams = self.allNgrams[n-2]
                    ngramSentence = ngramSentences[n-2]
                    for i in xrange(lastIdx - n):
                        ngram = s[i:i+n]
                        ngramId = ngramIds.get(ngram)
                        if ngramId is None:
                            ngramId = len(ngrams)
                            ngramIds[ngram] = ngramId
                            ngrams.append(ngram)
                        ngramSentence.add(ngramId)
            for n in ngramRange:
                self.ngramCorpora[n-2].append(sorted(ngramSentences[n-2]))


    def main_distribution(self, k):
        """Used to optimize random sampling."""
        return 1. / (k * math.log(1 - 1. * k / (len(self.corpus) + 1)))
        #return 1. / (math.log(1 - 1. * k / (len(self.corpus) + 1)))
        #return 1


    def run(self, timeout, nbNewAlignments):
        """Extract alignments from subcorpus loaded into memory.

        -- timeout: float
            This is less than or equal to the "-t" command line argument (less
            if not all-in-memory).
        -- nbNewAlignments: int
            The "-a" command line argument.
        """
        nbLines = len(self.corpus)
        if nbLines > 2: # Speed up by not using subcorpora of size 1 or nbLines
            nextRandomSize = Distribution(
                self.main_distribution,
                2,              # Never get sample size = 1
                nbLines - 1     # Never get sample size = nbLines
                ).next
        else:   # Use the theoritically correct distribution
            nextRandomSize = Distribution(
                self.main_distribution,
                1,
                nbLines
                ).next

        nb2 = 0     # Number of subcorpora of size 2
        nbSubcorporaDone = 0
        subcorporaDoneSum = 0 # for calculating average size
        previousNbAl = 0
        previousWriteLen = 0
        lastWriteTime = startTime = time()
        speed = sys.maxint

        print >> sys.stderr, "\rAligning... (ctrl-c to interrupt)"
        # Do not compress this temp file ! Some alignments are not actually
        # written with KeyboardInterrupt (may be because of psyco)
        tmpFile = make_temp_file(".al")
        try:
            try:
                while speed > nbNewAlignments:
                    t = time()
                    if timeout is not None and t - startTime >= timeout:
                        break
                    elapsedTime = t - lastWriteTime
                    if nbSubcorporaDone >= 1 and elapsedTime >= 1:
                        speed = int(math.ceil((self.nbAlignments -
                                               previousNbAl) / elapsedTime))
                        #proba = (1 - 2. / (nbLines + 1)) ** (2 * nb2)
                        toWrite = "(%i subcorpora, avg=%.2f) " \
                                  "%i alignments, %i al/s" % \
                                  (nbSubcorporaDone,
                                   1. * subcorporaDoneSum / nbSubcorporaDone,
                                   self.nbAlignments, speed)
                        message("\r%s%s" % (toWrite," " * (previousWriteLen -
                                                           len(toWrite))))
                        previousWriteLen = len(toWrite)
                        previousNbAl = self.nbAlignments
                        lastWriteTime = t
                    
                    
                    subcorpusSize = nextRandomSize()
                    while subcorpusSize > MAX_SUBCORPUS_SIZE:
                        subcorpusSize = nextRandomSize()
                    if subcorpusSize == 2:
                        nb2 += 1
                    
                    nbSubcorporaDone += 1
                    subcorporaDoneSum += subcorpusSize
                    self.align(random.sample(xrange(nbLines), subcorpusSize),
                               tmpFile)
            except KeyboardInterrupt:
                toWrite = "(%i subcorpora, avg=%.2f) Alignment interrupted! " \
                          "Proceeding..." % (nbSubcorporaDone,
                                             1. * subcorporaDoneSum
                                             / nbSubcorporaDone)
            else:
                toWrite = "(%i subcorpora, avg=%.2f) Alignment done, " \
                          "proceeding... " % (nbSubcorporaDone,
                                              1. * subcorporaDoneSum
                                              / nbSubcorporaDone)
            print >> sys.stderr, "\r%s%s" % \
                  (toWrite, " " * (previousWriteLen - len(toWrite)))
            
            if nbLines > 2:
                # Add alignments from subcorpora of sizes 1 and nbLines
                weight1 = 2 * nb2 * math.log(1 - 2. / (nbLines + 1)) \
                          / (nbLines * math.log(1 - 1. / (nbLines + 1)))
                weightN = 2 * nb2 * math.log(1 - 2. / (nbLines + 1)) \
                          / (nbLines * math.log(1 -
                                                1. * nbLines / (nbLines + 1)))
                if weight1:
                    frac1, weight1 = math.modf(weight1)
                    weight1 = int(weight1)
                    for i in xrange(nbLines):
                        w = weight1
                        if random.random() < frac1:
                            w += 1
                        if w:
                            self.align([i], tmpFile, w)
                if weightN:
                    fracN, weightN = math.modf(weightN)
                    w = int(weightN)
                    if random.random() < fracN:
                        w += 1
                    if w:
                        self.align(xrange(nbLines), tmpFile, w)
            
            tmpFile.seek(0)
            self.weightFunc(tmpFile)
        finally:
            tmpFile.close()


    def align(self, lineIds, outputFile, weight=1):
        """Get all possible alignments from the specified corpus lines.

        -- lineIds: iterable(int)
            The line ids to look up (indices in self.corpus)
        -- outputFile: file
        -- weight: int

        1) Associate to each n-gram the list of lines it appears on.
        Then, n-grams that strictly appear on the same lines are
        grouped together;
        2) for each of these groups, we go through the lines they
        appear on. For each line, we output the selected words in the
        correct order, if the resulting alignment verifies the
        filtering constraints. We also output the complementary on
        each line if it verifies these constraints as well.

        Alignments written to <outputFile> have the same format as the
        original corpus. Abslolute frequencies are kept in memory
        (self.counts), using <weight> as unit. All words are written
        in hexadecimal.
        
        """
        
        corpus = self.corpus
        languageRange = range(self.nbLanguages)
        ngramRange = range(2, self.indexN + 1)

        vec_word = {}   # {tuple(int): set(int)}
        vw_setdefault = vec_word.setdefault
        
        for n in xrange(1, self.indexN + 1):
            
            
            if n == 1:
                word_ap = {}
                wa_setdefault = word_ap.setdefault
                for lineId in lineIds:
                    for word in corpus[lineId]:
                        vec = wa_setdefault(word, [lineId])
                        if vec[-1] != lineId:
                            vec.append(lineId)
                # Group words according to the lines they appear on.
                for word, linesAp in word_ap.iteritems():
                    vw_setdefault(tuple(linesAp), set()).add(word)
            else:
                ngram_ap = {}
                na_setdefault = ngram_ap.setdefault
                ngramCorpus = self.ngramCorpora[n-2]
                for lineId in lineIds:
                    for ngram in ngramCorpus[lineId]:
                        na_setdefault(ngram, []).append(lineId)
                for ngram, linesAp in ngram_ap.iteritems():
                    vw_setdefault(tuple(linesAp), set()
                                  ).update(self.allNgrams[n-2][ngram])

            # Above part was changed with new option "-i", rest is identical
            

            minNbWords = self.minLanguages + self.minSize - 1
            for linesAp, wordSet in vec_word.iteritems():
                # Check if there are enough words
                if len(wordSet) < minNbWords:
                    continue
                
                # Check if there are words in at least minLanguages
                l = set()
                for word in wordSet:
                    l.add(self.wordLanguages[word])
                    if len(l) == self.minLanguages:
                        break
                if len(l) < self.minLanguages:
                    continue

                #wordSet = set(wordSet) # Now it is a a set already
                
                for lineId in linesAp:
                    words = corpus[lineId]
                    perfect = [[] for _ in languageRange]
                    context = [[] for _ in languageRange]
                    for wordPos, word in enumerate(words):
                        l = self.wordLanguages[word]
                        if word in wordSet:
                            perfect[l].append(wordPos)
                        else:
                            context[l].append(wordPos)
                            
                    for candidate in (perfect, context):
                        nbLanguages = 0
                        for languageId, phrase in enumerate(candidate):
                            # Check for contiguity
                            if (self.contiguousFields[languageId] and phrase
                                and phrase[-1] - phrase[0] != len(phrase) - 1):
                                candidate[languageId] = []
                            # Check for length
                            elif not (self.minSize <= len(phrase)
                                      <= self.maxSize):
                                candidate[languageId] = []
                            
                            if candidate[languageId]:
                                nbLanguages += 1
                        
                        if nbLanguages < self.minLanguages:
                            continue

                        for i, phrase in enumerate(candidate):
                            prev = None
                            newPhrase = []
                            for wordPos in phrase:
                                if self.delimiter and prev is not None and \
                                   wordPos != prev + 1:
                                    newPhrase.append(0)
                                newPhrase.append(words[wordPos])
                                prev = wordPos
                            candidate[i] = newPhrase

                        stringToPrint = '\t'.join([' '.join([hex(w)[2:]
                                                             for w in phrase])
                                                   for phrase in candidate])
                        alString = '\t'.join([' '.join([self.allWords[w]
                                                            for w in phrase])
                                                  for phrase in candidate])
                        bucket = self.counts.setdefault(len(alString), {})
                        alHash = hash(alString)
                        alFreq = bucket.get(alHash)
                        if alFreq is None:
                            bucket[alHash] = weight
                            print >> outputFile, stringToPrint
                            self.nbAlignments += 1
                        else:
                            bucket[alHash] = alFreq + weight


    def _dummy_weight(self, inputFile):
        """Simply replace word ids by original strings.

        -- inputFile: file

        Add a dash instead of computing lexical weights.
        
        """
        del self.corpus # We don't need it anymore
        nbSplits = self.nbLanguages - 1
        for line in inputFile:
            print >> self.weightedAlignmentFile, "%s\t-" % \
                  '\t'.join([' '.join([self.allWords[int(word, 16)]
                                       for word in phrase.split()])
                             for phrase in line.split('\t', nbSplits)])

    def _lexical_weight(self, inputFile):
        """Compute lexical weights and replace word ids by original strings.

        -- inputFile: file
        
        """
        FH = len(self.wordFreq) - self.wordFreq.count(1)    # First Hapax

        # Make all words appear at most once on all lines and remove hapaxes:
        # since they occur only once, there is no need to remember how many
        # times they appear along with other words (always 1);
        for lineId, line in enumerate(self.corpus):
            self.corpus[lineId] = [word for word in set(line) if word < FH]

        # Compute a maximum for progress percentage
        lastLanguage = self.nbLanguages - 1
        nbSourceWords = 0
        for word in xrange(FH):
            if self.wordLanguages[word] != lastLanguage:
                nbSourceWords += 1

        # Dump alignment counts into temporary file to save memory
        dictFile = make_temp_file(".dict.gz")
        zDictFile = gzip.GzipFile(fileobj=dictFile, mode="wb", compresslevel=1)
        try:
            for alLength, c in self.counts.iteritems():
                print >> zDictFile, hex(alLength)[2:]
                for alHash_freq in c.iteritems():
                    print >> zDictFile, "%x %x" % alHash_freq
            zDictFile.close()
            self.counts.clear()
            
            message("\rComputing word cooccurrences...\n")
            nextPercentage = Progression(nbSourceWords).next
            coocDb = CoocDB(FH)
            # Modify corpus in place: remove a whole language, index its
            # words, re-read corpus to compute how many times each of these
            # words appear with words from all other languages. Do this until
            # only one language remains.
            for sourceLanguage in xrange(lastLanguage):
                sourceAp = {}
                for lineId, line in enumerate(self.corpus):
                    newLine = []
                    for word in line:
                        if self.wordLanguages[word] == sourceLanguage:
                            sourceAp.setdefault(word, []).append(lineId)
                        else:
                            newLine.append(word)
                    self.corpus[lineId] = newLine
                
                # Force the progress percentage to grow uniformly
                sources = sourceAp.keys()
                random.shuffle(sources)
                for sw in sources:
                    cooc = {}
                    for lineId in sourceAp[sw]:
                        for tw in self.corpus[lineId]:
                            cooc[tw] = cooc.get(tw, 0) + 1
                    if cooc:
                        coocDb.add(sw, cooc)
                    nextPercentage()
                del sourceAp
            
            del self.corpus

            message("\rComputing lexical weights...\n")
            nextPercentage = Progression(self.nbAlignments).next
            nbSplits = self.nbLanguages - 1

            for line in inputFile:
                alignment0 = [[int(word, 16) for word in phrase.split()]
                              for phrase in line.split('\t', nbSplits)]
                # Copy of alignment0 without discontinuity separator
                alignment = [[word for word in phrase if word]
                             for phrase in alignment0]

                # Get a local copy of word cooccurrences, including hapaxes
                cooc = {}
                for srcLang in xrange(lastLanguage):
                    targets = alignment[srcLang+1:]
                    for sw in alignment[srcLang]:
                        c = cooc.setdefault(sw, {})
                        if sw < FH:
                            for target in targets:
                                for tw in target:
                                    if tw < FH:
                                        if tw not in c:
                                            c[tw] = coocDb.get(sw, tw)
                                    else:
                                        c[tw] = 1
                        else:
                            for target in targets:
                                for tw in target:
                                    c[tw] = 1

                # Compute lexical weights
                lexWeights = []
                for srcLang, sourcePhrase in enumerate(alignment):
                    lexWeight = 1.
                    for sw in sourcePhrase:
                        sourceFreq = self.wordFreq[sw]
                        highestCooc = 0
                        for tgtLang, targetPhrase in enumerate(alignment):
                            if srcLang == tgtLang:
                                continue
                            for tw in targetPhrase:
                                if srcLang < tgtLang:
                                    newCooc = cooc[sw][tw]
                                else:
                                    newCooc = cooc[tw][sw]
                                highestCooc = max(highestCooc, newCooc)
                        lexWeight *= 1. * highestCooc / sourceFreq
                    lexWeights.append(lexWeight)
                
                # Replace word ids by original strings
                print >> self.weightedAlignmentFile, "%s\t%s" % \
                      ('\t'.join([' '.join([self.allWords[word]
                                            for word in phrase])
                                  for phrase in alignment0]),
                       ' '.join(["%f" % lw for lw in lexWeights]))
                nextPercentage()

            del coocDb  # Release memory?

            # Recover alignment counts from temporary file
            dictFile.seek(0)
            zDictFile = gzip.GzipFile(fileobj=dictFile, mode="rb")
            c = None
            for line in zDictFile:
                numbers = line.split(" ", 1)
                if len(numbers) == 1:
                    c = self.counts.setdefault(int(numbers[0], 16), {})
                else:
                    c[int(numbers[0], 16)] = int(numbers[1], 16)
            zDictFile.close()
        finally:
            dictFile.close()


###############################################################################
# Main program
###############################################################################

def main():
    """Process command line options."""
    parser = optparse.OptionParser(version=__version__,
                                   description="""Check out
http://users.info.unicaen.fr/~alardill/anymalign/ for more!""",
                                   usage='''(basic usage)
    python %prog corpus.source corpus.target >translationTable.txt

For more control:
    python %prog [INPUT_FILE[.gz|.bz2] [...]] >ALIGNMENT_FILE
    python %prog -m [ALIGNMENT_FILES[.gz|.bz2] [...]] >ALIGNMENT_FILE

INPUT_FILE is a tab separated list of aligned sentences (1/line):
<sentenceNlanguage1> [<TAB> <sentenceNlanguage2> [...]]

A generated ALIGNMENT_FILE has the same format as INPUT_FILE (same
fields), plus three extra fields at the end of each line:
1) a space-separated list of lexical weights (1/language);
2) a space-separated list of translation probabilities (1/language);
3) an absolute frequency:
<phraseNlanguage1> [...] <TAB> <lexWeights> <TAB> <probas> <TAB> <frequency>

ALIGNMENT_FILES is the concatenation of several ALIGNMENT_FILE's.''')

    parser.add_option('-m', '--merge', default=False, action='store_true',
                      help="""Do not align. Input files are
pre-generated alignment files (plain text format) to be merged into a
single alignment file.""")
    parser.add_option('-T', '--temp-dir', dest='dir', default=None,
                      help="""(compatible with -m) Where to write
temporary files. Default is OS dependant.""")
    parser.add_option('-q', '--quiet', default=False, action='store_true',
                      help="""(compatible with -m) Do not show
                      progress information on standard error.""")

    alterGroup = optparse.OptionGroup(parser,
                                      "Options to alter alignment behaviour")
    alterGroup.add_option('-a', '--new-alignments', dest='nb_al', type='int',
                      default=-1, help="""Stop alignment when number of
new alignments per second is lower than NB_AL. Specify -1 to run
indefinitely. [default: %default]""")
    alterGroup.add_option('-i', '--index-ngrams', dest='index_n', type='int',
                      default=1, help="""Consider n-grams up to
n=INDEX_N as tokens. Increasing this value increases the number of
long n-grams output, but slows the program down and requires more
memory [default: %default]""")
    alterGroup.add_option('-S', '--max-sentences', dest="nb_sent", default=0,
                          type='int', help="""Maximum number of
sentences (i.e. input lines) to be loaded in memory at once. Specify 0
for all-in-memory. [default: %default]""")
    alterGroup.add_option('-t', '--timeout', dest='nb_sec', type='float',
                          default=-1, help="""Stop alignment after
NB_SEC seconds elapsed. Specify -1 to run indefinitely. [default:
%default]""")
    alterGroup.add_option('-w', '--weight', default=False, action='store_true',
                      help="""Compute lexical weights (requires
additional computation time and memory).""")
    parser.add_option_group(alterGroup)

    filteringGroup = optparse.OptionGroup(parser, "Filtering options")
    filteringGroup.add_option('-D', '--discontiguous-fields', dest='fields',
                              default='', help="""Allow discontiguous
sequences (like "give up" in "give it up") in languages at positions
specified by FIELDS. FIELDS is a comma-separated list of integers
(1-based), runs of fields can be specified by a dash (e.g.
"1,3-5").""")
    filteringGroup.add_option('-l', '--min-languages', dest='nb_lang',
                              type='int', default=None, help="""Keep
only those alignments that contain words in at least MIN_LANGUAGES
languages (i.e. columns). Default is to cover all languages.""")
    filteringGroup.add_option('-n', '--min-ngram', dest='min_n', type='int',
                              default=1, help="""Filter out any
alignment that contains an N-gram with N < MIN_N. [default:
%default]""")
    filteringGroup.add_option('-N', '--max-ngram', dest='max_n', type='int',
                              default=7, help="""Filter out any
alignment that contains an N-gram with N > MAX_N (0 for no
limit). [default: %default]""")
    parser.add_option_group(filteringGroup)

    formattingGroup = optparse.OptionGroup(parser, "Output formatting options")
    formattingGroup.add_option('-d', '--delimiter', dest='delim', type='str',
                               default='', help="""Delimiter for
discontiguous sequences. This can be any string. No delimiter is shown
by default. Implies -D- (allow discontinuities in all languages) if -D
option is not specified.""")
    formattingGroup.add_option('-e', '--input-encoding', dest='encoding',
                               default='utf-8', help="""(compatible
with -m) Input encoding. This is useful only for HTML and TMX output
formats (see -o option). [default: %default]""")
    formattingGroup.add_option('-L', '--languages', dest='lang', type='str',
                               default=None, help="""(compatible with
-m) Input languages. LANG is a comma separated list of language
identifiers (e.g. "en,fr,ar"). This is useful only for HTML (table
headers) and TMX (<xml:lang>) output formats (see -o option).""")
    formattingGroup.add_option('-o', '--output-format', dest='format',
                               type='str', default='plain',
                               help="""(compatible with -m) Output
format. Possible values are "plain", "moses", "html", and "tmx".
[default: %default]""")
    parser.add_option_group(formattingGroup)

    options, args = parser.parse_args()
            
    if args.count("-") > 1:
        parser.error('Standard input "-" can only be read once')
    if not args:    # Read standard input
        args = ["-"]

    global __verbose__, __tmpDir__
    __verbose__, __tmpDir__ = not options.quiet, options.dir
    if 'psyco' in globals():
        message("Using psyco module\n")

    format = options.format.lower()
    if "plain".startswith(format):
        writer = PlainWriter(sys.stdout)
    elif "moses".startswith(format):
        writer = MosesWriter(sys.stdout)
    elif "html".startswith(format):
        writer = HTMLWriter(sys.stdout, options.encoding, options.lang)
    elif "tmx".startswith(format):
        writer = TMXWriter(sys.stdout, options.encoding, options.lang)
    else:
        parser.error("Unknown output format for option -o")

    if options.merge:
        merge(args, writer)
    else:
        try:    # Check whether the -D option value is well formed
            parse_field_numbers(options.fields, 0)
        except ValueError:
            parser.error("Invalid field list for option -D")
        if options.delim and not options.fields:
            options.fields = "-"
        if options.max_n <= 0:
            options.max_n = sys.maxint
        if options.index_n < 1:
            parser.error("-i option must be positive")
        if options.index_n > options.max_n:
            parser.error(
                "-i option value should not be greater than that of -N")
        
        Aligner(args, writer, options.nb_al, options.nb_sent, options.nb_sec,
                options.weight, options.fields, options.nb_lang, options.min_n,
                options.max_n, options.delim, options.index_n)


if __name__ == '__main__':
    try:
        import psyco
    except ImportError:
        pass
    else:
        #psyco.log()
        # Allow KeyboardInterrupt to be raised in main loop
        psyco.cannotcompile(Aligner.run)
        psyco.full()

    #import doctest
    #from StringIO import StringIO
    #doctest.testmod()
    #sys.exit()

    main()
