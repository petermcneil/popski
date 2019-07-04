.PHONY: clean upload serve

upload: clean
	scripts/aws-update.py -d

serve: clean
	JEKYLL_ENV="dev" jekyll serve

clean:
	rm -rf _site
	rm -rf /tmp/popski
