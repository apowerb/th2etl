<p align="center">
  <img src="https://docs.apowerb.com/logo/apowerb-wide.png" alt="apowerb" height="80"/>
</p>

<p align="center">
  <strong>ETL and automation library for the apowerb stack — pipelines modelled as stages of blocs.</strong>
</p>

<p align="center">
  <a href="https://docs.apowerb.com/">Documentation</a> •
  <a href="https://github.com/apowerb/th2etl">GitHub</a> •
  <a href="https://thaink2.com">thaink2</a>
</p>

---

## What is this image?

th2etl runs ETL and automation pipelines for the
[**apowerb**](https://github.com/apowerb/apowerb) stack.

A pipeline is modelled as a series of **stages**, each containing one or more **blocs**.
Stages run sequentially: the next one starts only once every bloc of the current stage
has completed successfully.

## Quick start

```bash
docker run -d --name th2etl \
  -e DATABASE_URL=postgresql://... \
  apowerb/th2etl:latest
```

See the [orchestration guide](https://docs.apowerb.com/configuration/orchestration) for
how th2etl fits into the stack.

## Tags

| Tag | Content |
|-----|---------|
| `latest` | Latest published release |
| `x.y.z` | A specific release |

## License

Apache-2.0. Source and issues on [GitHub](https://github.com/apowerb/th2etl).
