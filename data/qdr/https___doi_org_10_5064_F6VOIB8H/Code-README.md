# IASGE Survey Data Analysis

## About
This book focuses on preparing and analyzing survey data downloaded from Qualtrics for analysis, as a part of the [Investigating & Archiving the Scholarly Git Experience](https://investigating-archiving-git.gitlab.io/) project. We are providing all the data and code openly to facilitate reuse, reproducibility, and extension of our work.

## Build our book locally
1. Install R & RStudio
2. Install the bookdown, RMarkdown, and tinytex packages in RStudio with the following two commands in the R terminal:
	* `install.packages(c("rmarkdown", "bookdownplus", "tinytex", "webshot", "tidyverse", "here", "ggplot2", "knitr", "kableExtra", "tidytext", "tidyr", "ggpubr", "stringr"))`
  	* `tinytex::install_tinytex()`
	* `webshot::install_phantomjs()`
	
	You can also click Tools > Install Packages and type the package names (make sure "install dependencies" is checked) separated by commas.
	
3. Go to the project folder and double click `survey-analysis.Rproj` to start RStudio
4. Run this command in the R Console after RStudio opens: `bookdown::render_book('index.Rmd', 'all')`
5. Go to the folder `_book` in the project folder and click `index.html` to view the book locally in your browser.

## Contact info
You are welcome to email me at [vicky dot steeves at nyu dot edu](mailto:vicky.steeves@nyu.edu) if you have questions or concerns, or raise an issue on this repository and I will do my best to respond quickly!
