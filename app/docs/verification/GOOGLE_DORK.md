# Google Dork

Domain-only setup now includes a `google_dork` collector after RDAP and before social OSINT/AI. It builds four bounded queries with `site:<root-domain>`: public PDFs, about/contact/news pages, API/docs/developer pages, and public Office documents. The collector never downloads result pages and drops every search result whose hostname is outside the project's `allowed_domains`.

When configured with an existing Google Custom Search JSON API key and Programmable Search Engine ID (`GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID`), the backend makes at most four API calls per collection and requests up to five results per query. Search snippets and links are stored as `google_dork` sources; in-scope URLs/hostnames become discovered assets. Snippets remain candidate evidence and do not prove ownership.

Google says the Custom Search JSON API is closed to new customers and existing customers must transition by January 1, 2027. Without existing API access, the collector reports `skipped` and the Collection logs show clickable Google Search links for manually running each query. It does not scrape Google result pages or claim that those searches ran automatically. See [Google's API status and requirements](https://developers.google.com/custom-search/v1/overview).

Automated tests cover domain scoping, out-of-scope result rejection, persisted snippets/assets, request bounds, and manual-link fallback. No paid Google API call was made for verification.
