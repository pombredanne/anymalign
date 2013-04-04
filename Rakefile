require "pp"
require 'rake/clean'

TEMP_DIR = "tmp"

src_beamer = FileList[ 'beamer-*.tex' ]
dep_beamer = FileList[ 'beamer/**/*' ]
rakefile   = FileList[ "Rakefile"   ]

def pdf_for(tex_file)
  File.basename(tex_file,'.tex') + '.pdf'
end

def xelatex(tex_file,*options)
  pdf_file = pdf_for(tex_file)
  sh(*[
     "xelatex",
     #'-shell-escape',
     "-interaction",'batchmode',
     "--output-directory=#{TEMP_DIR}",
     tex_file
  ])
  mv "#{TEMP_DIR}/#{pdf_file}", pdf_file
rescue
  puts "error compiling #{tex_file}"
end

task :autoclean do
  CLEAN.include "#{TEMP_DIR}/*"
  CLEAN.include "*.pyg"
  Rake::Task['clean'].invoke
end

desc "compile beamer*.tex"
task :beamer do
  src_beamer.each do |beamer|
    unless uptodate? pdf_for(beamer), [beamer,dep_beamer,rakefile].flatten
      xelatex beamer
    end
  end
end

task :watch do
  loop do
    Rake::Task[:beamer].invoke
    puts "sleeping @#{Time.now}"
    sleep 1
  end
end
task :default => [:beamer, :autoclean]
