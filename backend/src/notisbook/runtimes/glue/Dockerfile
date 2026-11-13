# Runtime Notisbook sobre AWS Glue 5.0 (Spark 3.5, Python 3.11, Java 17).
# A imagem base já exporta SPARK_HOME e PYTHONPATH (PyGlue.zip + pyspark) via ENV,
# então pyspark/awsglue importam em `docker exec` sem shell de login.
# Executar com `docker run -d --init`: sem init a JVM deixa processos zumbis. O
# ENTRYPOINT da base é `bash -l` e encerra sem TTY, por isso é redefinido abaixo.
FROM public.ecr.aws/glue/aws-glue-libs:5@sha256:a54bd25fb72c55a2f28d07656a3cda943a042f345cc25f4c2c170667be864f01

USER root
# ipykernel fica no site-packages do sistema (persistente), não em ~/.local.
RUN python3 -m pip install --no-cache-dir "ipykernel==7.4.0"
USER hadoop

ENTRYPOINT ["sleep", "infinity"]
