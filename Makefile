.PHONY: clean upload serve install

upload: clean
	scripts/aws-update.py -d

serve: clean
	JEKYLL_ENV="dev" jekyll serve

clean:
	rm -rf _site
	rm -rf /tmp/popski

install:
	gem install bundler
	bundler install
