POP-SKI 
=======

This is the master repository which holds all of the different versions of my website - popski

First version - S3
------------------
I first built this site with a static website hosted on S3. 
Hand-written HTML, JS, and CSS files were used to build the site. I used this as learning
time for some really basic HTML, CSS, and JS. It wasn't the best... (and still isn't). 


The site is served out of S3 with Cloudfront as a CDN, and TLS certificate provided by
Amazon Certificate Manager. 

To ensure that the website is updated immediately I have written a script to invalidate
the Cloudfront CDN. It backups old sites and gzips content to reduce bandwidth.

I am extremely aware that this site looks _awful_, however I would like to caveat by saying
that I am not a natural front-end/designy person. I am working towards improving my skills in 
this area.