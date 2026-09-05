# Media Reach Split Planner Web

Client-side Media Reach Planner.

## Current version
Web **0.42**

## Architecture
- Static site only
- No backend
- No database
- No authentication
- Uploaded media plans are processed locally in the browser
- `index.html` is the production application

## Deployment
The intended production host is Netlify. Once continuous deployment is connected to the `main` branch, every commit to `main` should publish automatically.


Deployment status: Netlify continuous deployment enabled and verified on 2026-09-03.


## Web 0.51

Reach aggregation is calculated as a bounded audience union across flights/lines instead of arithmetic Reach summing. The web UI validates the invariant Reach < 100% and does not silently cap invalid results.
