# observium-cmdline-95th-percentile
Generate 95th Percentile values from your customer interfaces in Observium for the previous month, or for the current month so far.

- Reference your observium config.php file, to automatically connect to the DB and discover your interfaces marked with "Cust:" in the description
- Send an email summary or display to the console
- Generate values for the previous month, or for the current month so far

#### Configuration

At the top of bill95.py you'll find SMTP configuration variables.  Here you can specify the from address as well as the SMTP server to use.

#### Variables

Below are the command line arguments you can supply

```

--observium-config  Path to your observium configuration file
--email <emailaddress>  Specifying this will send an email, and not print anything to the terminal
--prev  This will generate 95th percentile values for the previous month
--rrd-base  Specify the base path of your rrd files.  It defaults to /opt/observium/rrd if nothing is supplied

```

#### Automate it?

Run this in cron.  I'm running it on the 1st of the month, to generate values for the previous month
