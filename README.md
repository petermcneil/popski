Popski
---
A personal website written by Peter McNeil. Using Jekyll as the static generator
 with S3 as hosting.

CSS/HTML/JS are all painstakingly written by myself through self-teaching.

#### Scripts
`aws-update` is a script that will upload the statically generated website to S3 and 
invalidate cloudfront with a flag `-i`. Needs cleaning up.

Invalidation of Cloudfront is done by working out what files have changed in the fully built 
website have changed via Git. This works well for ensuring that expensive cache invalidations
aren't wasted on resources that have not been updated.