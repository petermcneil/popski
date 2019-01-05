Popski
---
A personal website written by Peter McNeil - using Jekyll as the static generator
 with S3 as hosting.

CSS/HTML/JS are all painstakingly written by myself through self-teaching.

#### Scripts
`aws-update` is a script that will build and upload the statically generated website to S3, with the 
 option to invalidate cloudfront.

Invalidation of Cloudfront is done by working out what files have changed in the fully built 
website have changed via Git. This works well for ensuring that expensive cache invalidations
aren't wasted on resources that have not been updated.