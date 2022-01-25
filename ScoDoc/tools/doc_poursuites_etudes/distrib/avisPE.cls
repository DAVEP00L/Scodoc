%% Original : Cléo BARAS
%%
%% Version 1.0
%%
%% Ce fichier est distribué par ScoDoc
%%
%% Si vous voulez le modifier sur le serveur, copiez le dans
%% ../local/
%% et éditez votre copie dans local.
%%

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{avisPE}
  [2017/05/06 v0.1 Modele avis PE]

\LoadClass[12pt]{article}
\RequirePackage{ifthen}
\RequirePackage{array}
\RequirePackage[paper=a4paper,textwidth=190mm]{geometry}
\RequirePackage{bookman}
\RequirePackage{xcolor}
\RequirePackage{fontawesome}

   %%%%%%%%%%%%%%%%%%%%%%%%%%%
   % Mise en page par défaut %
   %%%%%%%%%%%%%%%%%%%%%%%%%%%

\setlength{\textwidth}{190mm}    %% Largeur de la zone texte
\setlength{\textheight}{300mm}    %% Hauteur de la zone texte
\setlength{\topmargin}{-25mm}
\setlength{\evensidemargin}{-15mm}
\setlength{\oddsidemargin}{-15mm}  

\definecolor{ugared}{rgb}{0.94,0.02,0.02}
\definecolor{ugadarkgray}{rgb}{0.72,0.72,0.72}
\definecolor{ugagray}{rgb}{0.42,0.42,0.42}
\definecolor{ugablack}{rgb}{0,0,0}

\pagestyle{empty} % pour ne pas indiquer de numéro de page...

% On définit les pieds de page comme des \stretch de force 1,
% soit 4 plus fort que celui qui est en bas du chapeau
% (Cf. ci-dessous). De cette façon, un avis qui ne remplit pas toute la
% page a un bel espacement.
\makeatletter
\def\@textbottom{\vspace*{\stretch{1}}}
\makeatother

  
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
   %      Paramètres réglables          %
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% L'utilisateur peut les redéfinir ceux-ci «\renewcommand» si besoin :
\newcommand{\espaceInterRubrique}{\medskip\vspace{\stretch{0.1}}}

\newlength{\rubriquedureeparindent} 
\setlength{\rubriquedureeparindent}{-16pt}

   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
   %     Macros pratiques       %
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\def\er{$^{\hbox{er}}$}
\def\ere{$^{\hbox{ère}}$}
\def\eme{$^{\hbox{ème}}$}


   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
   % L'environnement "rubrique" %
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Usage : \begin{rubrique}[Indentation]{Titre} [...] \end{rubrique}
% On met le texte qu'on veut à l'intérieur.

\newenvironment{nom}   % "rubrique" prend un seul argument, le titre
{
\relax%
\noindent
\medskip\bfseries	 \LARGE}{%
\normalsize\normalfont
\espaceInterRubrique
}

\newenvironment{rubrique}[1]   % "rubrique" prend un seul argument, le titre
{
\relax%
\noindent
\tikz{\fill[ugagray]  (0,0) rectangle (0.5cm,0.5cm); }
%\faArrowCircleRight
\medskip\hspace{0.2cm}\bfseries		\color{ugagray} \Large{#1}\par
\noindent\tikz{\fill[white]  (0,0) rectangle (0.5cm,0.5cm); 
\draw[ugagray] (0.8cm,1cm)--(19cm,1cm); }\par
		\color{ugablack}\normalsize\normalfont}{% le contenu
\espaceInterRubrique
}

\newenvironment{sousrubrique}[1]   % "rubrique" prend un seul argument, le titre
{\espaceInterRubrique\relax%
		\color{ugagray}{\faCaretSquareORight~\textbf{\large{#1}}}
		\color{ugablack}\normalsize\normalfont\par%
		\espaceInterRubrique
		}{}


   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
   %    L'en-tête de l'avis     %
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% en paramètre: le logo
\newenvironment{entete}[1]{% 
	\def\ligne{\rule[2pt]{24pt}{1pt}} % Ligne séparatrice
	\noindent
	\begin{minipage}{\linewidth}%\hspace{-2cm}%
		\begin{minipage}{5.5cm}
			\includegraphics[height=3.5cm,keepaspectratio=true]{#1}
		\end{minipage}
		\hfill
		\begin{minipage}{13cm}
		\color{ugagray}
}
{		\color{ugablack}
\relax\vspace*{\fill}
\end{minipage}
\end{minipage}
\vspace{\stretch{0.25}}}
