# Nommage, environnements et exposition

## NOM-01 : nom du service
Le nom du service est en minuscules, commence par une lettre, ne contient que des lettres, des chiffres et des
tirets, et fait de 3 à 31 caractères. Exemples valides : `catalogue-api`, `paiement-front`. Invalides :
`Catalogue_API`, `api` suivi d'espaces.

## NOM-02 : namespace Kubernetes
Chaque service exposé vit dans son propre namespace, nommé `svc-<service>-<environnement>`, par exemple
`svc-catalogue-api-dev`. Le namespace porte les labels `netco.io/service` et `netco.io/environment`.

## ENV-01 : environnements
Trois environnements existent : `dev`, `recette` et `prod`. Une demande sans environnement, ou avec un autre
environnement, est incomplète : elle ne peut pas être traitée.

## EXP-01 : type d'exposition
- `interne` : le service n'est joignable que depuis les zones réseau NetCo demandées (voir [zones.md](zones.md)).
- `externe` : le service est en plus joignable depuis Internet (zone `internet`). Une exposition externe impose le
  port 443 (voir [ports.md](ports.md)).
