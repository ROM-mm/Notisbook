# Runtime Notisbook sobre AWS Glue 6.0 (Spark 4.1, Scala 2.13, Python 3.13, Java 17).
# A imagem base já exporta SPARK_HOME e PYTHONPATH (PyGlue.zip) e traz o pyspark no
# site-packages, então pyspark/awsglue importam em `docker exec` sem shell de login.
# Executar com `docker run -d --init`: sem init a JVM deixa processos zumbis. O
# ENTRYPOINT da base é `bash -l` e encerra sem TTY, por isso é redefinido abaixo.
FROM public.ecr.aws/glue/aws-glue-libs:6.0@sha256:0faef080664f0043c4dda5ad387a3177e01364dc4f65eac15e2fed322b6975ac

USER root
# ipykernel fica no site-packages do sistema (persistente), não em ~/.local.
RUN python3 -m pip install --no-cache-dir "ipykernel==7.4.0"
USER hadoop

ENTRYPOINT ["sleep", "infinity"]
