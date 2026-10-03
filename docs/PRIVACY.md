# Privacy

This is a private home weather application in a public source repository.

Never commit:
- exact home address;
- HOME_LAT / HOME_LON;
- .env;
- Google/Cloudflare credentials;
- tokens, cookies or private runtime logs.

The UI/API may expose the logical location id `home`, but not its coordinates.

Public DWD station metadata such as station_05480 may be committed.

WeatherNext evidence stored in GitHub must remain sanitized and must not include private credential material or private home coordinates.
