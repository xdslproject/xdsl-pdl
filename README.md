# PDL experiments in xDSL

A repository with PDL experiments in xDSL.

## Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Scripts

* `analyze-pdl-rewrite`: Analyze the given PDL rewrite. If no rewrites are provided, generate a random one.
* `generate-pdl-rewrite`: Generate a random PDL rewrite.
* `generate-pdl-matches`: Generate random PDL matches for a given PDL rewrite.
