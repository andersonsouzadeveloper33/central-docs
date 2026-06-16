"""
Script de migração R2: move todos os objetos para o prefixo do tenant.
Executa UMA ÚNICA VEZ após a migração do banco.
"""
import boto3
from botocore.config import Config

TENANT_ID     = "29e713d4-893f-4a38-b82a-de764fabad8f"
CF_ACCOUNT_ID = "0527279a58ca34c6f7759899a64d07e3"
CF_ACCESS_KEY = "7a3ac7882e63a79d2192d547e7b03f1d"
CF_SECRET_KEY = "17f05bbe4c37afe9dfbb368fce4cf74af7e219ea65c5183607b6f241015e6656"
CF_BUCKET     = "centraldocs"
CF_ENDPOINT   = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

r2 = boto3.client(
    "s3",
    endpoint_url=CF_ENDPOINT,
    aws_access_key_id=CF_ACCESS_KEY,
    aws_secret_access_key=CF_SECRET_KEY,
    config=Config(signature_version="s3v4"),
)

def list_all_objects():
    objects = []
    paginator = r2.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=CF_BUCKET):
        for obj in page.get("Contents", []):
            objects.append(obj["Key"])
    return objects

def migrate():
    objects = list_all_objects()
    if not objects:
        print("Nenhum objeto encontrado no bucket.")
        return

    to_migrate = [k for k in objects if not k.startswith(TENANT_ID + "/")]
    already_ok = [k for k in objects if k.startswith(TENANT_ID + "/")]

    print(f"Total de objetos: {len(objects)}")
    print(f"Já migrados: {len(already_ok)}")
    print(f"Para migrar: {len(to_migrate)}")

    if not to_migrate:
        print("Nada a migrar.")
        return

    print()
    for old_key in to_migrate:
        new_key = f"{TENANT_ID}/{old_key}"
        print(f"  Copiando: {old_key}")
        print(f"       →   {new_key}")
        try:
            r2.copy_object(
                Bucket=CF_BUCKET,
                CopySource={"Bucket": CF_BUCKET, "Key": old_key},
                Key=new_key,
            )
            r2.delete_object(Bucket=CF_BUCKET, Key=old_key)
            print(f"       ✓ OK")
        except Exception as e:
            print(f"       ✗ ERRO: {e}")

    print("\nMigração concluída.")

if __name__ == "__main__":
    print("=== Migração R2 — CentralDocs ===\n")
    confirm = input(f"Isso vai mover todos os arquivos para o prefixo '{TENANT_ID}/'. Continuar? (s/n): ")
    if confirm.strip().lower() == "s":
        migrate()
    else:
        print("Cancelado.")
