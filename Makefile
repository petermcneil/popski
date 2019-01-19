upload:
	scripts/aws-update.py ${args}

serve:
	JEKYLL_ENV="dev" jekyll serve