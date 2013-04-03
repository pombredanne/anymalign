require "pp"
require 'rake/clean'

TEMP_DIR = "tmp"
CLEAN.include "#{TEMP_DIR}/*"

template = FileList[ 'cjk.*'      ]
markdown = FileList[ '*.markdown' ]
conf     = FileList[ "Rakefile"   ]
source = markdown + template + conf

def error(string)
  puts [
    "#"*50,
    "\n",
    ">"*5,
    string,
    "\n",
    "#"*50,
  ].join""
end

def pandoc(*args)
  sh "pandoc",*args
rescue
  error "error running pandoc with #{args.inspect}"
end


def pdflatex(pdf,tex)
  begin
    sh "pdflatex",                            \
      "-interaction",'batchmode',             \
      "-jobname", File.basename(pdf,'.pdf'),  \
      "--output-directory=#{TEMP_DIR}",tex
  rescue
    error "error generating #{pdf}"
  end
  begin
    mv "#{TEMP_DIR}/#{pdf}", pdf
  rescue
    error "error moving #{pdf}"
  end
end

tex = {
  beamer: (markdown.ext '.beamer.tex'),
  outline:(markdown.ext '.outline.tex'),
}
pdf = {
  beamer: (markdown.ext '.beamer.pdf'),
  outline:(markdown.ext '.outline.pdf'),
}

CLOBBER.include tex.values.flatten
CLOBBER.include pdf.values.flatten

desc "create beamer.tex from markdown"
task :tex_beamer => source do
  pairs = tex[:beamer].zip(markdown)
  pairs.each do |beamer,md|
    next if uptodate?(beamer,[md])
    pandoc                    \
      "-t","beamer+raw_tex",  \
      "--template=cjk",       \
      md,"-o",beamer
  end
end

desc "create beamer.pdf from beamer.tex"
task :pdf_beamer => :tex_beamer do
  pdf[:beamer].zip(tex[:beamer]).each do|pdf,tex|
    next if uptodate?(pdf,[tex])
    pdflatex pdf, tex
  end
end

desc "create outline.tex from markdown"
task :tex_outline => source do
  pairs = tex[:outline].zip(markdown)
  pairs.each do |beamer,md|
    next if uptodate?(beamer,[md])
    pandoc                    \
      "-t","latex+raw_tex",  \
      "--template=cjk",       \
      md,"-o",beamer
  end
end

desc "create outline.pdf from outline.tex"
task :pdf_outline => :tex_outline do
  pdf[:outline].zip(tex[:outline]).each do|pdf,tex|
    next if uptodate?(pdf,[tex])
    pdflatex pdf, tex
  end
end

desc "generate all pdf files"
task :all => [:pdf_outline, :pdf_beamer]

task :default => [:all]
