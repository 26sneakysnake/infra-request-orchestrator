# Runbooks réseau

## RB-01 : zone autorisée bloquée par la NetworkPolicy
Symptômes : les pods sont prêts et le Service a des endpoints prêts, mais une zone qui devrait joindre le service
est bloquée.
Vérifications : comparer les zones et le port de la NetworkPolicy (`fromZones`, `ports`) avec la demande
validée. Une zone absente, ou un port différent de celui du service, bloque le trafic légitime.
Cause : NetworkPolicy non conforme à la demande (`network_policy`).
Action autorisée : `reapply_network_policy`.

## RB-02 : ports du Service incohérents
Symptômes : les pods sont prêts, le Service a des endpoints prêts, la NetworkPolicy autorise bien la zone, mais
la zone autorisée n'obtient pas de réponse.
Vérifications : le `port` du Service doit être le port demandé, et son `targetPort` doit être le port sur lequel
le conteneur écoute (`containerPorts`, journal « Starting up on port … »).
Cause : ports du Service incohérents (`service_port`).
Action autorisée : `reapply_service`.

## RB-03 : selector du Service sans pod
Symptômes : les pods sont prêts mais le Service n'a aucun endpoint prêt (`ready endpoints 0`).
Vérifications : comparer le selector du Service avec les labels des pods. Une faute de frappe ou un label absent
des pods laisse le Service sans cible.
Cause : selector du Service erroné (`service_selector`).
Action autorisée : `reapply_service`.
