build:
	scripts/aws-update.py

serve:
	JEKYLL_ENV="dev" jekyll serve